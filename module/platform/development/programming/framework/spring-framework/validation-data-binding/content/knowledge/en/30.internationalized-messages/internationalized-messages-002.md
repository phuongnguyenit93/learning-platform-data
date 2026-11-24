# MessageSourceResolvable and Resolving ObjectError or FieldError

## 1. Why Do Validation Errors Need Message Resolution?

A Spring Framework application typically uses the same set of validation rules for many users, while error messages must match each user's language and context.

For example, the same “username is required” error can be displayed as:

- Vietnamese: **Tên đăng nhập không được để trống**.
- English: **Username must not be blank**.

You should not hardcode Vietnamese directly into every `@NotBlank(message="...")` or concatenate strings from `FieldError#getField()`. Doing so makes it hard to share one validator across multiple languages, hard to customize messages per form, and couples the API to the provider's default phrasing.

Spring assigns three key roles:

1. **`MessageSourceResolvable`**: *describes a message translation request*: candidate codes, template arguments, and a default message.
2. **`ObjectError` / `FieldError`**: *describes an error on an object or property*, and also implements `MessageSourceResolvable` so it can be translated.
3. **`MessageSource`**: *the message resolver* based on codes and `Locale`, for example reading `messages.properties` and `messages_vi.properties`.

The single most important line when turning an error into a user-facing message is:

```java
String text = messageSource.getMessage(error, locale);
```

Here `error` is an `ObjectError` or `FieldError` (or any `MessageSourceResolvable`). This call prioritizes looking up the codes carried by the error, applies arguments when formatting, and falls back to the default message only if needed.

## 2. What Does MessageSourceResolvable Contain?

The interface lives in `org.springframework.context.MessageSourceResolvable`. Its three main methods are:

```java
// Illustrative API signatures, not an interface to define yourself.
String[] getCodes();
Object[] getArguments();
String getDefaultMessage();
```

In the current API, these values can be `null`. The table below clarifies their roles:

| Member | Function | Example |
| --- | --- | --- |
| `getCodes()` | Ordered list of message codes to try, from specific to general | `NotBlank.signupForm.username`, `NotBlank.username`, `NotBlank.java.lang.String`, `NotBlank` |
| `getArguments()` | Values inserted into placeholders via `MessageFormat`; may contain another resolvable | Localized field name, limit value, constraint parameter |
| `getDefaultMessage()` | Fallback message if no matching code is found | `must not be blank` |

**The first code does not always exist in the bundle.** `MessageSource` tries each code in order; a more general code may end up being used.

Some implementations and inheritance relationships:

```text
MessageSourceResolvable (interface)
      │
      └── DefaultMessageSourceResolvable
                 │
                 └── ObjectError (global/object-level error)
                          │
                          └── FieldError (field-level error)
```

`DefaultMessageSourceResolvable` is an implementation you can construct directly for any message. `ObjectError` is an object-level error, and `FieldError` is a subtype of `ObjectError` that adds property-specific metadata.

### getCode() vs. getCodes()

`DefaultMessageSourceResolvable#getCode()` usually returns the **last code** in the list—that is, the most general code, such as `NotBlank`. By contrast, `getCodes()[0]` is typically the highest-priority code, such as `NotBlank.signupForm.username`.

Do not use `getCode()` as the sole lookup key and ignore the specific codes. When you already have a `MessageSourceResolvable`, pass **the entire object** to `MessageSource#getMessage(resolvable, locale)` to preserve code fallback ordering.

## 3. How Do ObjectError and FieldError Differ?

### 3.1. ObjectError: An Error for the Entire Object

`org.springframework.validation.ObjectError` represents an error not tied to a single property. For example, a registration form has `password` and `confirmPassword` that are each valid on their own, but the two values do not match.

In a Spring `Validator`, you can record a global error:

```java
if (!Objects.equals(form.getPassword(), form.getConfirmPassword())) {
    errors.reject(
        "passwordMismatch",
        new Object[]{"Password"},
        "Passwords do not match");
}
```

This is an **illustrative snippet inside a `validate` method**, requiring `form`, `errors`, and an `Objects` import. `errors.reject(...)` records a **global error**.

An `ObjectError` provides:

- `getObjectName()`: for example `signupForm`.
- `getCodes()`, `getArguments()`, `getDefaultMessage()` provided by the resolvable mechanism.
- `getCode()`: usually the general code at the end of the list.
- `contains(Class<?>)` and `unwrap(Class<?>)`: depending on the case, can retrieve the wrapped source exception or `ConstraintViolation` wrapped via `wrap(...)`.

With `errorCode=passwordMismatch` and `objectName=signupForm`, `DefaultMessageCodesResolver` typically generates:

```text
passwordMismatch.signupForm
passwordMismatch
```

If `messages_vi.properties` contains `passwordMismatch.signupForm`, Spring prefers the form-specific message over the general `passwordMismatch`.

### 3.2. FieldError: An Error on a Single Property

`org.springframework.validation.FieldError` extends `ObjectError` and adds:

- `getField()`: the invalid field, e.g., `username` or `shippingAddress.zipCode`.
- `getRejectedValue()`: the rejected value (do not arbitrarily log it or return it to clients).
- `isBindingFailure()`: indicates whether the error came from binding/type conversion rather than a regular validation check.
- `getObjectName()`, `getCodes()`, `getArguments()`, `getDefaultMessage()` as in `ObjectError`.

Custom Spring validator example:

```java
if (form.getUsername() == null || form.getUsername().isBlank()) {
    errors.rejectValue(
        "username",
        "required",
        new Object[]{"Username"},
        "Username is required");
}
```

This is an illustrative snippet using `Errors.rejectValue`. Spring creates a `FieldError` with field `username` and a code sequence derived from the object name and field type. With object name `signupForm`, type `String`, and code `required`, the typical list is:

```text
required.signupForm.username
required.username
required.java.lang.String
required
```

Similarly, a `typeMismatch` error when the binder fails to convert `"abc"` to `Integer` can be represented by a `FieldError` with `isBindingFailure() == true`.

**Distinguish the source:** `FieldError` does not only come from Jakarta Bean Validation; it can originate from `WebDataBinder`, a Spring `Validator`, or explicit `rejectValue(...)` calls.

### 3.3. Error Retrieval Methods on BindingResult

`BindingResult` extends `Errors` and provides:

| API | Meaning |
| --- | --- |
| `hasErrors()` | Whether there are any errors |
| `getAllErrors()` | Every `ObjectError`, including `FieldError` instances |
| `getGlobalErrors()` | Only object-level errors |
| `getFieldErrors()` | Only property-level errors |
| `getFieldErrors("username")` | List of errors for a specific property |
| `getFieldError("username")` | First error for the property, may be `null` |
| `getErrorCount()` | Total number of errors |
| `getObjectName()` | Name of the bound object |

Common display pattern:

```java
for (ObjectError error : result.getAllErrors()) {
    String text = messageSource.getMessage(error, locale);

    if (error instanceof FieldError fieldError) {
        System.out.println(
            fieldError.getField() + ": " + text);
    } else {
        System.out.println("form: " + text);
    }
}
```

This is an **integration fragment**, where `result` is a `BindingResult` and `messageSource` and `locale` are already available. Since `ObjectError` also covers `FieldError`, use `instanceof FieldError` to branch rather than implicitly assuming every `ObjectError` is a global error.

## 4. How Does DefaultMessageCodesResolver Order Codes?

Spring uses `MessageCodesResolver`, defaulting to `DefaultMessageCodesResolver`, to generate a fallback code sequence from the base error code, object name, field name, and Java field type.

### 4.1. Object-level

Suppose `errors.reject("invalidCombination")` is called with object name `checkout`:

```text
invalidCombination.checkout
invalidCombination
```

### 4.2. Field-level

Suppose `errors.rejectValue("quantity","Min")`, object name `orderForm`, and field type `java.lang.Integer`:

```text
Min.orderForm.quantity
Min.quantity
Min.java.lang.Integer
Min
```

The order goes from *most specific* to *most general*:

1. Code specific to a field on a single form.
2. Code shared by all fields with the same name.
3. Code for the corresponding Java type.
4. General code for all fields with the same constraint/error code.

Note: errors placed into `BindingResult` by a Bean Validation provider may carry provider/adapter-specific argument structures. **Do not guess argument positions** solely from the name `Min` or `NotBlank`; inspect the actual codes/arguments in a real scenario before writing templates with `{0}`, `{1}`.

### 4.3. Nested Properties and Collection Indices

For a field like `addresses[0].zipCode`, the resolver can generate codes for both the specific index and the unindexed path, for example:

```text
typeMismatch.orderForm.addresses[0].zipCode
typeMismatch.orderForm.addresses.zipCode
typeMismatch.addresses[0].zipCode
typeMismatch.addresses.zipCode
typeMismatch.zipCode
typeMismatch.java.lang.String
typeMismatch
```

This illustrates a `String` field type. The exact number of codes, path names, and Java type depend on the actual property structure. The idea is that you can translate an error for a specific element or use a general code for all elements.

### 4.4. Customizing the Resolver

`DefaultMessageCodesResolver` allows configuring a prefix or code format, such as the `validation.` prefix. In MVC, if you want a custom resolver for binding, you can use `WebBindingInitializer` or an appropriate MVC configuration callback, but only do so when a naming convention has been agreed upon across the entire codebase.

Any change to code generation must be accompanied by updates to message bundles and tests; changing the prefix without updating `messages_vi.properties` can cause errors to fall back to the default message or throw `NoSuchMessageException`.

## 5. In What Order Does MessageSource Resolve Messages?

The `org.springframework.context.MessageSource` interface has three common overloads:

```java
String getMessage(
    String code, Object[] args, String defaultMessage, Locale locale);

String getMessage(
    String code, Object[] args, Locale locale);

String getMessage(
    MessageSourceResolvable resolvable, Locale locale);
```

These are **simplified API signatures**; the actual interface includes nullable annotations and corresponding parameter types.

When calling `messageSource.getMessage(fieldError, locale)`, Spring essentially:

1. Obtains the codes from `fieldError.getCodes()` in order.
2. Tries looking up the first code in the message source matching `locale`.
3. If not found, tries the next code and the message source's locale fallback steps.
4. Once a pattern is found, resolves arguments and uses `java.text.MessageFormat` when needed to substitute `{0}`, `{1}`, etc.
5. If no code is found, uses `getDefaultMessage()` if available.
6. If both a matching code and a default message are missing, the resolvable overload can throw `NoSuchMessageException`.

**`MessageSourceResolvable` does not read translation files itself.** It is the data describing the request; `MessageSource` performs the actual lookup.

Bundle example:

```properties
# messages_vi.properties
required.signupForm.username=Ten dang nhap khong duoc de trong
required=Truong nay la bat buoc
passwordMismatch.signupForm=Hai mat khau khong khop
```

And:

```properties
# messages_en.properties
required.signupForm.username=Username must not be blank
required=This field is required
passwordMismatch.signupForm=Passwords do not match
```

The blocks above use ASCII text to illustrate keys/values; real applications can store full diacritic Vietnamese using UTF-8. In `.properties` files, a key containing dots is an ordinary key string, not Java property-access syntax.

If a bundle contains both `required.signupForm.username` and `required`, an error on `signupForm.username` selects the first key. Another field like `signupForm.email`, if lacking a specific key, can fall back to `required`.

## 6. Standalone Example, Java 17 + Spring Framework 6.2.6

This example does not need an HTTP server. It creates a `BeanPropertyBindingResult` for a form, explicitly records two `FieldError`s and one `ObjectError`, configures a `StaticMessageSource` for Vietnamese and English, and calls `getMessage(error, locale)`.

By using `StaticMessageSource`, the program verifies the **exact** lookup order without depending on classpath files or request locales.

### 6.1. File Structure

```text
message-resolution-demo/
├── pom.xml
└── src/main/java/demo/MessageResolutionDemo.java
```

### 6.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>message-resolution-demo</artifactId>
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
    </plugins>
  </build>
</project>
```

`spring-context` pulls in the Spring modules needed for `StaticMessageSource` and `BeanPropertyBindingResult`. Java 17 suffices for this sample; `spring-boot-starter-web`, a Servlet container, or a Jakarta Validation provider are not required because the errors are created directly through the Spring `Errors` API.

### 6.3. MessageResolutionDemo.java

```java
package demo;

import java.util.Locale;

import org.springframework.context.support.DefaultMessageSourceResolvable;
import org.springframework.context.support.StaticMessageSource;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

public class MessageResolutionDemo {

    private static final Locale VI = Locale.forLanguageTag("vi-VN");
    private static final Locale EN = Locale.ENGLISH;

    // No HTTP binding runs: the DTO only provides field type metadata.
    public static class SignupForm {
        private String username;
        private String email;

        public String getUsername() {
            return username;
        }

        public void setUsername(String username) {
            this.username = username;
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }
    }

    private static void printError(
            String label,
            ObjectError error,
            StaticMessageSource messages) {

        System.out.println(
            label + " codes=" + String.join(" > ", error.getCodes()));

        System.out.println(
            label + " vi=" + messages.getMessage(error, VI));

        System.out.println(
            label + " en=" + messages.getMessage(error, EN));
    }

    public static void main(String[] args) {
        StaticMessageSource messages = new StaticMessageSource();

        messages.addMessage("label.username", VI, "Tên đăng nhập");
        messages.addMessage("label.username", EN, "Username");
        messages.addMessage("label.email", VI, "Email");
        messages.addMessage("label.email", EN, "Email");

        // Specific translation for one field of one form.
        messages.addMessage("required.signupForm.username", VI,
                "{0} không được để trống");
        messages.addMessage("required.signupForm.username", EN,
                "{0} must not be blank");

        // General translation serving as fallback for email and other fields.
        messages.addMessage("required", VI, "{0} là bắt buộc");
        messages.addMessage("required", EN, "{0} is required");

        // Object-level error.
        messages.addMessage("profileMismatch.signupForm", VI,
                "Hồ sơ không nhất quán");
        messages.addMessage("profileMismatch.signupForm", EN,
                "Profile is inconsistent");

        SignupForm form = new SignupForm();
        BeanPropertyBindingResult errors =
                new BeanPropertyBindingResult(form, "signupForm");

        // Arguments can also be resolvables => translates the field name.
        errors.rejectValue(
                "username",
                "required",
                new Object[] {
                    new DefaultMessageSourceResolvable("label.username")
                },
                "Username missing");

        errors.rejectValue(
                "email",
                "required",
                new Object[] {
                    new DefaultMessageSourceResolvable("label.email")
                },
                "Email missing");

        errors.reject(
                "profileMismatch", new Object[0], "Profile mismatch");

        FieldError username = errors.getFieldError("username");
        FieldError email = errors.getFieldError("email");
        ObjectError global = errors.getGlobalError();

        printError("USERNAME", username, messages);
        printError("EMAIL", email, messages);
        printError("GLOBAL", global, messages);

        // Code absent from the bundle: uses defaultMessage.
        DefaultMessageSourceResolvable missing =
                new DefaultMessageSourceResolvable(
                    new String[] {"missing.code"},
                    null,
                    "Thông báo dự phòng");

        System.out.println(
                "FALLBACK vi=" + messages.getMessage(missing, VI));
    }
}
```

The code calls `getFieldError(...)` and `getGlobalError()` right after adding the three errors itself, so there are no `null` values to guard against in this flow. In a real controller, always check for `null` or iterate over the error list.

### 6.4. Running the Program

Open a terminal in the folder containing `pom.xml`, with Java 17+ and Maven 3.x installed:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.MessageResolutionDemo
```

Output printed by `System.out.println` (excluding Maven/plugin logs if your environment prints any):

```text
USERNAME codes=required.signupForm.username > required.username > required.java.lang.String > required
USERNAME vi=Tên đăng nhập không được để trống
USERNAME en=Username must not be blank
EMAIL codes=required.signupForm.email > required.email > required.java.lang.String > required
EMAIL vi=Email là bắt buộc
EMAIL en=Email is required
GLOBAL codes=profileMismatch.signupForm > profileMismatch
GLOBAL vi=Hồ sơ không nhất quán
GLOBAL en=Profile is inconsistent
FALLBACK vi=Thông báo dự phòng
```

Result explanation:

- `USERNAME` has a specific key in `StaticMessageSource`, `required.signupForm.username`. Since it is the first code and has a translation, it beats the general `required` code.
- `EMAIL` has no specific translation, so Spring tries the specific codes and falls back to the general `required` code.
- `getArguments()` of both field errors contains a `DefaultMessageSourceResolvable` to look up `label.username` or `label.email` in the current locale. As a result, the display name is also translated.
- `GLOBAL` is an `ObjectError`, so it has two candidate codes, without field name or field type suffixes.
- `FALLBACK` demonstrates that `getDefaultMessage()` is used only when `missing.code` is not found.

This program **demonstrates the message resolution mechanism**; it does not start a Spring MVC controller, run Jakarta `@Valid`, or return HTTP statuses. When integrated with MVC, errors produced by `WebDataBinder` or Bean Validation may have different argument details and default messages.

## 7. Using MessageSource in a Spring Boot / Spring MVC Application

The standalone example uses `StaticMessageSource` to verify the logic. In a real web app, the standard approach is configuring message bundles.

### 7.1. Creating Locale-Specific Resources

In a Spring Boot application, bundles are normally placed under `src/main/resources`:

```text
src/main/resources/
├── messages.properties
├── messages_vi.properties
└── messages_en.properties
```

For example, `messages.properties` can hold the locale-independent default:

```properties
required=Value is required
profileMismatch=Profile information is inconsistent
```

In `messages_vi.properties` (saved as UTF-8):

```properties
NotBlank.signupForm.username=Tên đăng nhập không được để trống
NotBlank.username=Giá trị này không được để trống
NotBlank=Không được để trống
typeMismatch.signupForm.age=Tuổi phải là một số hợp lệ
profileMismatch.signupForm=Thông tin hồ sơ chưa nhất quán
```

In `messages_en.properties`:

```properties
NotBlank.signupForm.username=Username must not be blank
NotBlank.username=This value must not be blank
NotBlank=Must not be blank
typeMismatch.signupForm.age=Age must be a valid number
profileMismatch.signupForm=Profile information is inconsistent
```

The key `NotBlank.signupForm.username` only applies when the object name is `signupForm`, the field name is `username`, and the error code is `NotBlank`. If the controller uses `@ModelAttribute("registration")`, the object name changes, requiring bundle updates or relying on fallbacks like `NotBlank.username`/`NotBlank`.

This is an **integrated i18n message example**; you do not need to put it directly into the standalone Java project from Section 6.

### 7.2. MessageSource Bean and Encoding

Spring Boot normally auto-configures a `MessageSource` based on `messages*.properties` when matching bundle files exist. You can set:

```properties
# application.properties (if explicit configuration is desired)
spring.messages.basename=messages
spring.messages.encoding=UTF-8
```

Do not declare an extra `MessageSource` bean unintentionally, as it may alter resolution or parent-source behavior. In plain Spring Framework, you can declare a bean named `messageSource` of type `ResourceBundleMessageSource` or `ReloadableResourceBundleMessageSource` and configure its basename and encoding accordingly.

`MessageSource` is the **backend for retrieving messages**; it does not replace `Validator`. Having bundles without enabling validation in the controller will not produce errors, just as having `@NotBlank` without a Jakarta Validation provider will not enforce constraints along the expected path.

### 7.3. Selecting the Locale

In Spring MVC, `Locale` is usually obtained from the request's resolver, such as the `Accept-Language` header. In a handler or advice, you can accept a `Locale` parameter or call `LocaleContextHolder.getLocale()` when executing within the request context.

Example:

```java
@GetMapping("/locale-demo")
public String localeDemo(Locale locale, MessageSource messages) {
    // Illustrative syntax: MessageSource should not be assumed
    // to be a direct method argument resolver by default.
    return messages.getMessage(
        "welcome", null, "Hello", locale);
}
```

**Note:** The snippet above only illustrates the idea and is **not a recommended Spring MVC signature**, because `MessageSource` should be injected into the controller as a regular dependency. A properly designed example is:

```java
@RestController
public class LocaleDemoController {

    private final MessageSource messageSource;

    public LocaleDemoController(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    @GetMapping("/locale-demo")
    public String demo(Locale locale) {
        return messageSource.getMessage(
            "welcome", null, "Hello", locale);
    }
}
```

This is an integration fragment requiring imports and a `MessageSource` bean. Avoid using the server's `Locale.getDefault()` to pick translations for HTTP clients; it may not match the user's language.

### 7.4. ControllerAdvice for Returning Translated Errors

When a `@Valid @RequestBody` DTO is invalid, MVC normally throws `MethodArgumentNotValidException` if there is no adjacent `BindingResult` and nothing triggers whole-method validation.

An illustrative advice:

```java
@RestControllerAdvice
public class ValidationAdvice {

    private final MessageSource messages;

    public ValidationAdvice(MessageSource messages) {
        this.messages = messages;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<List<ApiError>> handle(
            MethodArgumentNotValidException ex,
            Locale locale) {

        List<ApiError> body = ex.getBindingResult()
            .getAllErrors()
            .stream()
            .map(error -> {
                String field = (error instanceof FieldError fe)
                    ? fe.getField() : "";
                String code = error.getCode();
                String text = messages.getMessage(error, locale);
                return new ApiError(field, code, text);
            })
            .toList();

        return ResponseEntity.badRequest().body(body);
    }

    public record ApiError(String field, String code, String message) {}
}
```

This is an **integration fragment**, requiring imports for the annotations, `ResponseEntity`, `List`, `MessageSource`, `MethodArgumentNotValidException`, and error classes. In production, consider how to categorize global errors, the HTTP contract, localization fallbacks, and keeping `code` stable for clients.

Key points in this fragment:

- Pass the **`ObjectError`/`FieldError` itself** to `messages.getMessage(error, locale)`, not just `error.getCode()`.
- Public error codes can be based on `error.getCode()` or stable application codes, without exposing every internal code in JSON.
- The translation **matches the request locale**.
- Do not return `FieldError#getRejectedValue()` directly because it can expose passwords, tokens, ID numbers, or sensitive data.

### 7.5. Method Validation and Spring WebFlux

In Spring MVC 6.1+, constraints directly on method parameters or return values can trigger built-in method validation and throw `HandlerMethodValidationException`. It uses result abstractions such as `MethodValidationResult` and `ParameterValidationResult` containing `MessageSourceResolvable` instances that can be translated with the same `MessageSource`.

With `@Validated` on a Spring service bean, AOP method validation may throw `ConstraintViolationException` or `MethodValidationException` depending on `MethodValidationPostProcessor#setAdaptConstraintViolations(...)`; do not catch only one exception type and assume all validation paths match.

In Spring WebFlux, argument validation and method validation exceptions operate in a different context than MVC, though the concept of representing errors as `MessageSourceResolvable` and translating them with `MessageSource` remains the same. This article focuses on the semantics and resolution of `ObjectError`/`FieldError` rather than prescribing a single exception handler for every web stack.

## 8. Handling Default Messages and NoSuchMessageException

There are three/four situations:

| Lookup Status | Outcome |
| --- | --- |
| Translation exists for highest-priority code | Use that translation |
| No specific translation, but general code exists | Try next code and use general code |
| No translation found, `getDefaultMessage()` is present | Use fallback message |
| No translation and no default message | May throw `NoSuchMessageException` |

Two overloads example:

```java
// Direct defaultMessage: returns fallback if code is not found.
String text = messageSource.getMessage(
    "unknown.code", null, "Fallback message", locale);

// No default provided: may throw NoSuchMessageException.
String strict = messageSource.getMessage(
    "unknown.code", null, locale);
```

This is a fragment; `messageSource` and `locale` are already injected/determined.

There is an option `AbstractMessageSource#setUseCodeAsDefaultMessage(true)` that uses the code itself as a fallback during development. However, **do not rely on it in production**, as users may see technical keys instead of friendly messages and missing message bundles may go unnoticed in tests.

**A default message is not a translation.** For instance, the provider may set an English default message; if no Vietnamese translation is found, showing the English default is an allowed fallback, but it does not fulfill multilingual requirements. Test bundles thoroughly for all supported locales and define an explicit fallback policy.

## 9. Arguments, MessageFormat, and Translatable Field Names

A message pattern with placeholders:

```properties
required={0} là bắt buộc
size.invalid={0} phải có từ {1} đến {2} ký tự
```

When arguments are supplied:

```java
new Object[] {
    new DefaultMessageSourceResolvable("label.username"),
    3,
    20
}
```

a message source that supports nested `MessageSourceResolvable` can:

1. Translate `label.username` to `Tên đăng nhập` for locale `vi-VN`.
2. Insert `Tên đăng nhập`, `3`, and `20` into the pattern using `MessageFormat`.
3. Produce the result: `Tên đăng nhập phải có từ 3 đến 20 ký tự`.

**Not all Bean Validation errors produce arguments in the same order.** Adapters may add field labels, annotation attributes, constraint values, or other argument types. Inspect `error.getArguments()` in an integration test before designing message templates with multiple placeholders.

### Single Quotes in MessageFormat

When a message has arguments, `MessageFormat` treats single quotes as escape delimiters. If a message contains a literal `'`, you may need to write it as `''` in the pattern. This is especially important for English messages containing `don't` or names with apostrophes; otherwise, the pattern may drop the quote or misparse placeholders.

### Semantics of getDefaultMessage()

If a resolvable has no matching code, its default message may also be formatted with arguments. Therefore, avoid setting a fallback pattern with the wrong placeholder count or order, especially when generated by a provider/adapter. For application-controlled content, choose simple, safe, tested defaults.

## 10. Distinguishing Error Codes, Field Names, and Messages

In API design, these data fields are often confused:

| Data | Example | Meaning |
| --- | --- | --- |
| `FieldError#getField()` | `username` | Server-side property name, not user-facing prose |
| `ObjectError#getObjectName()` | `signupForm` | Object name in the binding context |
| `getCodes()[0]` | `NotBlank.signupForm.username` | High-priority code for translation lookup |
| `getCode()` | `NotBlank` | General code, usually last in the list |
| `getDefaultMessage()` | `must not be blank` | Fallback pattern/sentence |
| `messageSource.getMessage(error, vi)` | `Tên đăng nhập không được để trống` | Message resolved for the locale |
| `FieldError#getRejectedValue()` | Client-submitted value | Potentially sensitive data, not a message |

**Do not use translated text as a public error code.** Clients should not have to parse Vietnamese strings to branch their logic. Return a stable machine-readable code (e.g., `VALIDATION_REQUIRED`) alongside the translated display text; the server can still use internal `NotBlank.*` codes for message lookup.

At the HTML form level, view engines such as Thymeleaf can use model attributes and binding results to display errors via appropriate tags/expressions. However, let the framework escape untrusted content; never build HTML by concatenating rejected values.

## 11. Common Pitfalls and How to Fix Them

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| `error.getDefaultMessage()` always shows English | Not using `MessageSource` / translation not found | Call `getMessage(error, locale)` and create proper bundles |
| `NotBlank.username` is not used | A more specific code was matched first | Inspect all `error.getCodes()` in order |
| `@NotBlank` on DTO produces no errors | Missing provider or `@Valid`/`@Validated` not triggered | Check validation starter, validator/groups, and MVC path |
| Field name in placeholder is not translated | Argument is a raw String or `label.*` is missing | Use a nested `MessageSourceResolvable` when appropriate |
| `NoSuchMessageException` | Missing key and no default message | Provide bundle/fallback and test locales |
| Strings with apostrophes render incorrectly | Pattern uses `MessageFormat` with unescaped quotes | Double single quotes when the pattern has arguments |
| Object-level errors are missing | Handler only iterates `getFieldErrors()` | Use `getAllErrors()` or also read `getGlobalErrors()` |
| Type conversion error treated as `@Min` | Confusing binding failure with validation failure | Check `FieldError#isBindingFailure()` |
| Messages appear in the wrong language | Locale taken from JVM/server instead of request | Use request locale via resolver/advice |
| Response leaks user password | Serializing raw `FieldError` or `getRejectedValue()` | Build a safe error DTO and audit field exposure |
| Hardcoding codes to Java parameter names | Object/field name changes on refactoring | Test codes and standardize public error codes |
| Bundle not found despite existing file | Mismatched basename, encoding, path, or locale suffix | Check `spring.messages.*` config and resource files |
| Client depends on Vietnamese messages | Machine code not separated from localized display | Return both a stable code and a translated message |

## 12. Testing Checklist

To verify the correctness of i18n validation:

1. For a specific `FieldError`, verify `getCodes()` contains the object name, field name, type, and fallbacks from the actual resolver.
2. When both a specific key and a general key exist, verify the specific key is chosen.
3. When the specific key is omitted, verify lookup falls back to the general key.
4. For an `ObjectError`, verify no out-of-context field codes are added.
5. When `getArguments()` contains a nested resolvable, verify both the field label and the main message are translated in the same locale.
6. For `NoSuchMessageException`, establish an appropriate default/fallback policy.
7. Test `vi-VN` and `en`, as well as an unsupported locale.
8. Check number, date, and apostrophe placeholders under `MessageFormat`.
9. On real forms, check both `BindingResult#getGlobalErrors()` and `getFieldErrors()`.
10. On API requests, verify responses contain no sensitive rejected values or stack traces.
11. When renaming `@ModelAttribute`, refactoring properties, or changing validation groups, re-run contract tests for message codes.
12. Distinguish JSON parse/type conversion errors, field validation, and method validation so advice catches the right exception types.

Unit tests on `StaticMessageSource` are great for understanding precedence and fallbacks. Integration tests with `MockMvc`/Spring context are required to confirm the codes actually generated by the binder/validator, the selected locale, and proper loading of message bundles.

## 13. Summary

**`MessageSourceResolvable` describes “which message needs to be resolved”, while `MessageSource` is the service that looks up translations by `Locale`.** `ObjectError` and `FieldError` implement the resolvable contract, so an error can be passed directly to `messageSource.getMessage(error, locale)`.

**`ObjectError`** represents an error for the entire object; **`FieldError`** adds the field name, rejected value, and binding-failure flag. Spring typically generates multiple message codes from specific to general using `DefaultMessageCodesResolver`. By defining bundles in the proper precedence order and keeping arguments and default messages consistent, you can share a single validation system across multiple languages without coupling clients directly to message text.

## Official References

- Spring Framework 6.2 — Internationalization using `MessageSource`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 Javadoc — `MessageSourceResolvable`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/context/MessageSourceResolvable.html
- Spring Framework 6.2 Javadoc — `MessageSource`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/context/MessageSource.html
- Spring Framework 6.2 Javadoc — `DefaultMessageSourceResolvable`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/context/support/DefaultMessageSourceResolvable.html
- Spring Framework 6.2 Javadoc — `ObjectError`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/ObjectError.html
- Spring Framework 6.2 Javadoc — `FieldError`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/FieldError.html
- Spring Framework 6.2 Javadoc — `DefaultMessageCodesResolver`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/DefaultMessageCodesResolver.html
- Spring Framework 6.2 Javadoc — `Errors` and `BindingResult`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/Errors.html
- Spring MVC 6.2 — Validation and form errors: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — Error responses & internationalization: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html