# @InitBinder in @Controller — Customizing Binding and Validation in Spring MVC

## 1. The Problem `@InitBinder` Solves

When a form sends data to Spring MVC, the incoming HTTP values are initially **strings**. The framework must resolve fields by name, convert types, and populate a Java object before the controller uses that object:

```http
POST /profiles/form
Content-Type: application/x-www-form-urlencoded

displayName=%20%20Linh%20%20&email=linh%40example.com&appointmentDate=31%2F12%2F2026&admin=true
```

For example, the DTO has `String displayName`, `String email`, `LocalDate appointmentDate`, and `boolean admin`. We want to:

- Normalize `displayName` by trimming leading and trailing whitespace.
- Parse the date according to the `dd/MM/uuuu` pattern instead of the default ISO format.
- Allow the client to modify only `displayName`, `email`, and `appointmentDate`; do **not** allow the form to set `admin` itself.
- Register a validator dedicated to that controller, combined with Jakarta Validation.
- When an error occurs, distinguish between **binding** errors (type conversion), **validation** errors (constraints), and **suppressed** fields (blocked by the allowlist).

`@InitBinder` is the configuration point for **`WebDataBinder`** before Spring uses the binder on matching request arguments. It does not perform all those operations itself: it only configures policies on the binder, while binding and validation are handled by the system in the next steps.

**Learning objectives:** understand the `@InitBinder` lifecycle, controller and model attribute scope, common operations on `WebDataBinder`, how `@ModelAttribute`/`@Valid`/`BindingResult` work together, limitations when encountering `@RequestBody`, and how to test this behavior with Java 17 + Spring Boot + MockMvc.

> **Scope:** Spring MVC Servlet stack, Jakarta Validation, Spring Framework 6.2.x / Spring Boot 3.5.x. WebFlux also has the binder concept, but its processing flow and exceptions differ; do not assume Servlet MVC signatures apply directly to WebFlux.

## 2. What Is `WebDataBinder`?

`org.springframework.web.bind.WebDataBinder` is the binder for web environments, extending `org.springframework.validation.DataBinder`. It can participate in:

1. **Binding:** assigning request parameters/form fields to properties or constructor arguments of the target object.
2. **Conversion:** converting `String` to `int`, `LocalDate`, enum, custom types, and so on.
3. **Formatting:** parsing strings using a custom format and formatting values for redisplay in a form.
4. **Validation:** using registered `org.springframework.validation.Validator` instances when validation is triggered.
5. **Binding policy:** restricting allowed fields, marking required fields, configuring auto-grow nested paths/collections.

`@InitBinder` is a method that Spring MVC calls to **configure the binder**, not an endpoint method that handles HTTP requests. A binder is bound to the matching target/object name context; do not store it in a static field or an arbitrary singleton.

Minimal example:

```java
@Controller
public class RegistrationController {

    @InitBinder
    void configure(WebDataBinder binder) {
        binder.setAllowedFields("name", "email");
    }

    @PostMapping("/register")
    String register(@ModelAttribute RegistrationForm form) {
        // ...
        return "success";
    }
}
```

This is an **illustrative snippet**, without the `RegistrationForm` definition or full imports. When Spring binds the form in this controller, properties not in the allowlist are not setter-bound. `@InitBinder` does not return `"success"` itself, does not handle requests in place of `@PostMapping`, and does not throw Bean Validation violations on its own.

## 3. Lifecycle: When Does Spring Call `@InitBinder`?

Overview for an `@ModelAttribute` form:

```text
HTTP request
   |
   v
DispatcherServlet selects @Controller + handler method
   |
   v
Argument resolver prepares model attribute
   |
   v
WebDataBinderFactory creates WebDataBinder
   |
   +--> @InitBinder in @ControllerAdvice (if applicable)
   |
   +--> @InitBinder in @Controller (if applicable)
   |
   v
Binder performs constructor/property binding and conversion
   |
   +--> Conversion error -> BindingResult FieldError
   |
   +--> Disallowed field -> suppressed fields
   |
   v
If @Valid / @Validated triggers -> binder.validate(...)
   |
   +--> Constraint error -> BindingResult FieldError/ObjectError
   |
   v
Handler receives object and BindingResult (if declared)
```

This is a **learning model**; certain details such as constructor binding and when the target is obtained depend on the argument resolver and model attribute. The core point: `@InitBinder` configures policies **before the binder executes its corresponding tasks**.

For each request, there may be multiple binders for different objects/arguments. Spring may invoke `@InitBinder` multiple times if a handler needs multiple binders. Therefore, this method should be **fast, side-effect-free, and not rely on being called exactly once**.

### 3.1. A Valid `@InitBinder` Method

```java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("name", "email");
}
```

Typically, it:
- Has a `void` return type.
- Accepts `WebDataBinder`, and optionally additional arguments supported by Spring for binder initialization.
- Is used to register editors, formatters, converters, validators, or policies.
- Is not `@RequestMapping`, and does not need a URL mapping.
- Does not receive a command object via an `@ModelAttribute` argument like a normal handler; Spring docs exclude `@ModelAttribute` from the supported arguments of `@InitBinder` methods.

## 4. Scope of Application: Controller, Model Attribute, and Controller Advice

### 4.1. `@InitBinder` Without a Specified Name

```java
@RestController
public class FormController {

    @InitBinder
    void configure(WebDataBinder binder) {
        binder.setAllowedFields("name", "email");
    }
}
```

The configuration belongs to **this controller** and does not automatically spread to every controller in the application. Because no attribute name is specified in the annotation, it can apply to binders associated with handler methods in this controller, so avoid setting an allowlist that only fits one DTO if the controller handles multiple different DTOs.

### 4.2. `@InitBinder("profileForm")` — Restricting by Object Name

```java
@InitBinder("profileForm")
void configureProfile(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email", "appointmentDate");
}

@PostMapping("/profiles")
public ResponseEntity<?> create(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult errors) {
    // ...
}
```

**Exact connection point:** the string `"profileForm"` on `@InitBinder` must match the **model attribute name** that the binder is processing. This name is neither a URL nor a Java method name. Explicitly declaring `@ModelAttribute("profileForm")` avoids relying on inferred names and is very useful when a controller has multiple forms.

You can use `@InitBinder({"profileForm", "settingsForm"})` to apply to two object names. Do not assume every annotation binds by class name or Java variable name: the actual object name determines binder selection.

### 4.3. `@ControllerAdvice` — Sharing Configuration Across Controllers

```java
@ControllerAdvice
public class CommonBindingAdvice {

    @InitBinder
    void configure(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
```

This is an **illustrative configuration snippet**, not included in the runnable project in section 9. When `@InitBinder` is placed in `@ControllerAdvice`, Spring can apply it across multiple controllers; `@ControllerAdvice` also provides selector attributes such as `basePackages`, `annotations`, and `assignableTypes` to narrow the scope.

Choose the placement based on intent:
- Rules specific to a single form/controller → `@InitBinder` in the controller and, if needed, specify the object name.
- Uniform rules across multiple endpoints → `@ControllerAdvice` or MVC config/`ConversionService`.
- Conversion rules for a widely used data type → usually register a global `Converter`/`Formatter` instead of duplicating logic across controllers.

Do not create a global allowlist that could drop fields on other DTOs without knowing every object name that the advice will handle.

## 5. `setAllowedFields` and Protection Against Mass Assignment

### 5.1. The Problem with Default Setter Binding

If a DTO has an `admin` property with a public setter:

```java
public class ProfileForm {
    private String displayName;
    private boolean admin;

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }
}
```

and the application binds the form through setters, a client can try sending `admin=true` even if the original HTML does not render this input. Hiding a field in the UI is **not** a data protection measure. This is an example of **mass assignment / over-posting**.

With `@InitBinder`:

```java
@InitBinder("profileForm")
void restrict(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email", "appointmentDate");
}
```

only the allowed field names undergo normal property binding. The `admin` field is **suppressed** instead of being set to `true` from the request. Suppressed fields can be inspected via:

```java
String[] suppressed = bindingResult.getSuppressedFields();
```

`BindingResult` is an object for reading errors/binding status in the handler, **not** a parameter of `@InitBinder`.

**Security note:** The learning example includes `admin` in the DTO to observe the suppression effect. A real application is better off using a **dedicated DTO containing only allowed fields** and never letting clients bind permission properties or internal IDs. An allowlist is one defensive layer and does not replace authorization in the service layer.

### 5.2. Allowlist Is Better Than Denylist

`binder.setAllowedFields(...)` is a *positive allowlist* and is **case-sensitive** per the Spring reference. `binder.setDisallowedFields(...)` can blacklist fields you do not want bound and matches patterns case-insensitively, but it becomes hard to maintain as models grow. The safer approach is to expose only the fields that may be edited, especially for nested properties.

Example:

```java
binder.setAllowedFields(
        "contact.email",
        "contact.phone",
        "addresses[0].city");
```

This is an illustrative fragment. The strings are **property paths** and may use wildcards according to the API. Before adding wildcards, carefully verify which nested paths are actually opened; `"addresses*"` is much broader than a single child property.

### 5.3. How Does `setDeclarativeBinding(true)` Differ from an Allowlist?

In Spring Framework 6.1+, `WebDataBinder` supports:

```java
@InitBinder
void configure(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

When declarative binding is enabled, Spring continues to allow **constructor binding** for parameters defined on the constructor, while **property/setter binding** does not happen automatically unless `allowedFields` is specified. This policy is especially suitable when DTOs are designed as immutable constructors or records.

If you use:

```java
binder.setDeclarativeBinding(true);
binder.setAllowedFields("displayName", "email");
```

then allowlisted fields can still be property-bound. **Do not misunderstand** `setAllowedFields` as a filter that blocks every constructor argument: constructor binding and property binding are two separate channels. When security matters, design the DTO constructor with only the intended public arguments.

In the complete example in section 9, we use a mutable form + allowlist to easily observe suppressed fields; we **do not enable declarativeBinding** in that project because we want to clearly demonstrate setter binding and formatter/editor behavior.

## 6. Normalizing Strings with `StringTrimmerEditor`

A request contains:

```text
displayName = "  Linh  "
```

After binding, you may want:

```text
displayName = "Linh"
```

In the controller:

```java
@InitBinder("profileForm")
void init(WebDataBinder binder) {
    binder.registerCustomEditor(
            String.class,
            "displayName",
            new StringTrimmerEditor(true));
}
```

Import `org.springframework.beans.propertyeditors.StringTrimmerEditor`. The `true` argument means a string that becomes empty after trimming is converted to **`null`**; for example, `"   "` becomes `null`. If `false` is used, a whitespace-only string becomes `""` after trimming instead of `null`.

Why register it only for `"displayName"`? Because:

```java
binder.registerCustomEditor(String.class, "displayName", editor);
```

registers the editor only for the **matching property path**. If you use the `registerCustomEditor(String.class, editor)` overload without a field name, you affect all `String` properties in that binder's scope, which may be inappropriate when passwords, tokens, or emails have different whitespace rules.

**Do not treat trimming as validation.** After conversion, `@NotBlank` or a custom validator still needs to check for invalid data. If trimming all-whitespace strings yields `null`, `@NotBlank` detects `null`; `@NotNull` may also be used depending on the contract.

## 7. Formatter and Converter: Changing How Types Are Parsed

A form may submit dates in a business format:

```text
appointmentDate=31/12/2026
```

In Java, the target property is `LocalDate`. Without a custom rule, the system may expect an ISO date like `2026-12-31`; depending on MVC configuration and format annotations, the string `31/12/2026` can cause a type mismatch.

### 7.1. Formatter Applied Only to the Form's Binder

```java
@InitBinder("profileForm")
void initProfile(WebDataBinder binder) {
    binder.addCustomFormatter(
            new Formatter<LocalDate>() {

                private final DateTimeFormatter pattern =
                        DateTimeFormatter.ofPattern("dd/MM/uuuu");

                @Override
                public LocalDate parse(String text, Locale locale) {
                    return LocalDate.parse(text, pattern);
                }

                @Override
                public String print(LocalDate date, Locale locale) {
                    return date.format(pattern);
                }
            },
            "appointmentDate");
}
```

This is an illustrative snippet for an `@InitBinder` method; it requires importing `Formatter`, `LocalDate`, `DateTimeFormatter`, and `Locale`. `DataBinder.addCustomFormatter(Formatter, String... fields)` scopes this formatter to a specific property path. `DateTimeFormatter` is immutable/thread-safe and safe to reuse across requests.

If the form sends `31/99/2026`, `LocalDate.parse` cannot convert the input; the binder records a conversion error in `BindingResult`. That is a **binding error**, not simply a `@NotNull` or `@Future` result.

### 7.2. For a Single Field, `@DateTimeFormat` Can Be Simpler

```java
@DateTimeFormat(pattern = "dd/MM/uuuu")
private LocalDate appointmentDate;
```

This is a declarative option and should be preferred when the format naturally belongs on the field and does not need per-controller configuration. Do not add both a local formatter and `@DateTimeFormat` to the same field without checking precedence: doing so can create confusing overlapping configuration.

### 7.3. Editor, Formatter, or Converter?

| Tool | Role | Best suited when |
| --- | --- | --- |
| `PropertyEditor` | Type conversion system based on `java.beans.PropertyEditor` (Spring wrapper/adapter) | Local customization, legacy compatibility cases |
| `Formatter<T>` | `parse` from String, `print` to String, `Locale`-aware | Formatting dates/currency/numbers displayed in forms |
| `Converter<S,T>` | Converts one source type to one target type | Conversion rules reused in many places |
| Global `FormattingConversionService` | Registers converters/formatters for multiple binders | Application-wide shared conventions |
| `@DateTimeFormat` | Annotation-driven field formatting | A single field/type with a clear format |

Do not use `@InitBinder` solely to fix Jackson JSON formatting; JSON body conversion goes through a different mechanism—see section 11.

## 8. Registering a Custom Validator at the Controller

`WebDataBinder` also supports:

```java
@InitBinder("profileForm")
void init(WebDataBinder binder) {
    binder.addValidators(new ProfileFormValidator());
}
```

`ProfileFormValidator` must implement `org.springframework.validation.Validator`:

```java
public class ProfileFormValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return ProfileForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        ProfileForm form = (ProfileForm) target;

        if ("blocked".equalsIgnoreCase(form.getDisplayName())) {
            errors.rejectValue(
                    "displayName",
                    "displayName.blocked",
                    "This name is not allowed");
        }
    }
}
```

This is an illustrative snippet without full imports; the complete code appears in section 9.

- `addValidators` **adds** a Spring validator; it does not remove the globally configured Jakarta Validation provider.
- `supports(Class<?>)` must match the class being validated by the binder. Registering a validator that does not support the target can cause configuration errors.
- `@Valid`/`@Validated` on the request argument causes Spring to invoke validation in matching flows. Simply adding a validator in `@InitBinder` does not guarantee every object is automatically validated if the handler has no validation trigger.
- `errors.rejectValue(...)` adds a field error with a custom code. This uses **Spring Validator/Errors**, which differs from writing a `jakarta.validation.ConstraintValidator`.
- If you want to reuse the same rule across multiple request DTOs outside MVC, consider a custom Jakarta constraint or a shared validator/service rather than hardcoding it in a controller-only binder.

## 9. Runnable Java 17 + Spring Boot Project

This example demonstrates five things in one application:
1. `@InitBinder("profileForm")` selects only the binder matching the object name.
2. `setAllowedFields` prevents the form from setting `admin` and records the suppressed field.
3. `StringTrimmerEditor` and the `LocalDate` formatter process form strings.
4. Jakarta Validation (`@NotBlank`, `@Email`, `@NotNull`) works alongside a custom Spring Validator when the handler has `@Valid`.
5. `@RequestBody` JSON goes through Jackson and **does not** use setter-based `WebDataBinder` property binding with `allowedFields`; the same controller also has another form that does not receive the `profileForm` policy.

### 9.1. Directory Structure

```text
init-binder-demo/
├── pom.xml
├── src/main/java/demo/binder/
│   ├── InitBinderApplication.java
│   ├── ProfileForm.java
│   ├── OtherForm.java
│   ├── ProfileFormValidator.java
│   └── ProfileController.java
└── src/test/java/demo/binder/
    └── ProfileControllerTest.java
```

### 9.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>init-binder-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-web` provides Spring MVC Servlet and Jackson. `spring-boot-starter-validation` provides the Jakarta Validation provider. `spring-boot-starter-test` provides JUnit Jupiter and MockMvc. The Boot parent selects compatible dependency versions; this is an illustrative project using Boot 3.5.6 and does not claim it to be the latest Spring Boot version.

### 9.3. `InitBinderApplication.java`

```java
package demo.binder;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InitBinderApplication {

    public static void main(String[] args) {
        SpringApplication.run(InitBinderApplication.class, args);
    }
}
```

### 9.4. `ProfileForm.java`

```java
package demo.binder;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.time.LocalDate;

public class ProfileForm {

    @NotBlank(message = "displayName.required")
    private String displayName;

    @NotBlank(message = "email.required")
    @Email(message = "email.invalid")
    private String email;

    @NotNull(message = "appointmentDate.required")
    private LocalDate appointmentDate;

    // Intentionally includes an admin setter to prove the allowlist blocks over-posting.
    private boolean admin;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public LocalDate getAppointmentDate() {
        return appointmentDate;
    }

    public void setAppointmentDate(LocalDate appointmentDate) {
        this.appointmentDate = appointmentDate;
    }

    public boolean isAdmin() {
        return admin;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }
}
```

In production code, it is best to **completely remove `admin` from the request DTO**. Here we keep it only to test binding suppression.

### 9.5. `OtherForm.java` — Verifying Annotation Scope

```java
package demo.binder;

public class OtherForm {

    private String memo;
    private boolean admin;

    public String getMemo() {
        return memo;
    }

    public void setMemo(String memo) {
        this.memo = memo;
    }

    public boolean isAdmin() {
        return admin;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }
}
```

`OtherForm` only serves as a **control case**: because its model attribute name differs from `profileForm`, its binder does not receive the custom allowlist in this example. This is not an authorization design pattern for real applications.

### 9.6. `ProfileFormValidator.java` — Local Spring Validator

```java
package demo.binder;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public class ProfileFormValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return ProfileForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        ProfileForm form = (ProfileForm) target;

        if ("blocked".equalsIgnoreCase(form.getDisplayName())) {
            errors.rejectValue(
                    "displayName",
                    "displayName.blocked",
                    "displayName is not allowed");
        }
    }
}
```

This rule does not call a DB or external system, and `supports` matches the `ProfileForm` type properly. In production, if a rule depends on I/O or user permissions, it is usually better to place that check in the service layer rather than a binder validator.

### 9.7. `ProfileController.java` — Main Part of the Lesson

```java
package demo.binder;

import jakarta.validation.Valid;
import org.springframework.beans.propertyeditors.StringTrimmerEditor;
import org.springframework.format.Formatter;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Arrays;
import java.util.Locale;
import java.util.Map;

@RestController
@RequestMapping("/profiles")
public class ProfileController {

    @InitBinder("profileForm")
    void initProfileForm(WebDataBinder binder) {

        // Only these fields are setter-bound from the form.
        binder.setAllowedFields(
                "displayName", "email", "appointmentDate");

        // Normalize the name, only for the displayName property.
        binder.registerCustomEditor(
                String.class,
                "displayName",
                new StringTrimmerEditor(true));

        // Form input: 31/12/2026 -> LocalDate 2026-12-31.
        binder.addCustomFormatter(new Formatter<LocalDate>() {

            private final DateTimeFormatter pattern =
                    DateTimeFormatter.ofPattern("dd/MM/uuuu");

            @Override
            public LocalDate parse(String text, Locale locale) {
                return LocalDate.parse(text, pattern);
            }

            @Override
            public String print(LocalDate date, Locale locale) {
                return date.format(pattern);
            }
        }, "appointmentDate");

        // Add custom validator without replacing global Bean Validation.
        binder.addValidators(new ProfileFormValidator());
    }

    @PostMapping(
            path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Map<String, Object>> submitForm(
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            var fields = errors.getFieldErrors().stream()
                    .map(error -> error.getField())
                    .distinct()
                    .sorted()
                    .toList();

            return ResponseEntity.badRequest().body(Map.of(
                    "status", "invalid",
                    "fields", fields,
                    "suppressed", Arrays.asList(
                            errors.getSuppressedFields())));
        }

        return ResponseEntity.ok(Map.of(
                "displayName", form.getDisplayName(),
                "email", form.getEmail(),
                "appointmentDate",
                form.getAppointmentDate().toString(),
                "admin", form.isAdmin(),
                "suppressed", Arrays.asList(
                        errors.getSuppressedFields())));
    }

    @PostMapping(
            path = "/other",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Map<String, Object> submitOther(
            @ModelAttribute("otherForm") OtherForm form) {

        return Map.of(
                "memo", form.getMemo(),
                "admin", form.isAdmin());
    }

    @PostMapping(
            path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> fromJson(
            @RequestBody ProfileForm form) {

        // JSON is deserialized by Jackson; this is not setter binding
        // from form parameters via WebDataBinder.
        return Map.of(
                "displayName", form.getDisplayName(),
                "admin", form.isAdmin());
    }
}
```

Key takeaways:

- `@InitBinder("profileForm")` applies configuration only when the binder has the corresponding object name.
- `@ModelAttribute("profileForm")` attaches an explicit name, avoiding reliance on Spring's name inference.
- `setAllowedFields` applies to **form setter/property binding**. `admin=true` is suppressed even though the DTO has a setter.
- `registerCustomEditor` affects only `displayName`; `email` is not automatically trimmed in this example.
- `addCustomFormatter` for `appointmentDate` converts `31/12/2026` to `LocalDate.of(2026, 12, 31)`.
- `addValidators` adds the custom `"blocked"` rule. `@Valid` causes the Jakarta provider and relevant Spring validators to run on the form.
- `BindingResult` sits **immediately after** `@ModelAttribute`; the handler receives binding/validation errors to return JSON containing `fields` instead of letting the framework throw `MethodArgumentNotValidException`.
- `errors.getSuppressedFields()` reveals which properties were skipped **due to binding policy**. A suppressed field **does not automatically make `errors.hasErrors()` true**; application policy must decide whether to reject requests with suppressed fields or simply ignore and record them.
- The `/other` endpoint demonstrates object-name scope: `otherForm` does not get `profileForm`'s allowlist. Having another endpoint accept `admin=true` in this demo is strictly to observe scoping and **must not be used as an authorization design in real applications**.
- The `/json` endpoint has no `@Valid`, so it does not trigger DTO validation there. It demonstrates that Jackson still reads `admin=true` and preserves whitespace in `displayName`; `@InitBinder` is not the solution for blocking JSON property assignment.

### 9.8. `ProfileControllerTest.java` — Testing with MockMvc

```java
package demo.binder;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProfileControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void allowedFieldsTrimDateAndSuppressAdmin() throws Exception {
        mvc.perform(post("/profiles/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "  Linh  ")
                        .param("email", "linh@example.com")
                        .param("appointmentDate", "31/12/2026")
                        .param("admin", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value("Linh"))
                .andExpect(jsonPath("$.appointmentDate")
                        .value("2026-12-31"))
                .andExpect(jsonPath("$.admin").value(false))
                .andExpect(jsonPath("$.suppressed[0]")
                        .value("admin"));
    }

    @Test
    void blankDisplayNameIsRejectedByBeanValidation()
            throws Exception {
        mvc.perform(post("/profiles/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "   ")
                        .param("email", "linh@example.com")
                        .param("appointmentDate", "31/12/2026"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value("invalid"))
                .andExpect(jsonPath("$.fields[0]")
                        .value("displayName"));
    }

    @Test
    void customValidatorRejectsBlockedName() throws Exception {
        mvc.perform(post("/profiles/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "blocked")
                        .param("email", "linh@example.com")
                        .param("appointmentDate", "31/12/2026"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0]")
                        .value("displayName"));
    }

    @Test
    void invalidDateIsBindingError() throws Exception {
        mvc.perform(post("/profiles/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "Linh")
                        .param("email", "linh@example.com")
                        .param("appointmentDate", "31/99/2026"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0]")
                        .value("appointmentDate"));
    }

    @Test
    void invalidEmailIsBeanValidationError() throws Exception {
        mvc.perform(post("/profiles/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "Linh")
                        .param("email", "not-an-email")
                        .param("appointmentDate", "31/12/2026"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0]")
                        .value("email"));
    }

    @Test
    void missingDateFailsNotNull() throws Exception {
        mvc.perform(post("/profiles/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "Linh")
                        .param("email", "linh@example.com"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0]")
                        .value("appointmentDate"));
    }

    @Test
    void otherFormDoesNotInheritProfileFormAllowlist()
            throws Exception {
        mvc.perform(post("/profiles/other")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("memo", "hello")
                        .param("admin", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.memo").value("hello"))
                .andExpect(jsonPath("$.admin").value(true));
    }

    @Test
    void jsonUsesJacksonNotFormPropertyBinding() throws Exception {
        mvc.perform(post("/profiles/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName": "  Linh  ",
                                  "email": "linh@example.com",
                                  "appointmentDate": "2026-12-31",
                                  "admin": true
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName")
                        .value("  Linh  "))
                .andExpect(jsonPath("$.admin").value(true));
    }

    @Test
    void isoDateIsNotTheFormFormatterPattern()
            throws Exception {
        mvc.perform(post("/profiles/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "Linh")
                        .param("email", "linh@example.com")
                        .param("appointmentDate", "2026-12-31"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0]")
                        .value("appointmentDate"));
    }
}
```

Run from the `init-binder-demo` directory, with JDK 17+ and Maven able to download dependencies:

```bash
mvn test
```

**All 9 tests are expected to pass.** Because `MockMvc` does not need to open an HTTP port, the tests go directly through Spring MVC argument resolution/binding/validation and verify status/JSON. Do not treat a test that directly calls `new ProfileController().submitForm(...)` as testing `@InitBinder`: plain Java calls do not run `DispatcherServlet` or the binder factory.

### 9.9. Why Do the Tests Prove Important Points?

| Test | What It Proves |
| --- | --- |
| `allowedFieldsTrimDateAndSuppressAdmin` | Allowlist, editor, and formatter work together; `admin` is suppressed yet the response is still 200 because there are no validation errors |
| `blankDisplayNameIsRejectedByBeanValidation` | Trims to `null` and `@NotBlank` catches the error via `@Valid` |
| `customValidatorRejectsBlockedName` | A Spring Validator added by `@InitBinder` can produce a `FieldError` |
| `invalidDateIsBindingError` | An invalid date string cannot convert to `LocalDate`; `BindingResult` records a type mismatch |
| `invalidEmailIsBeanValidationError` | Jakarta `@Email` is checked by the provider |
| `missingDateFailsNotNull` | Missing date input leaves the property `null` and violates `@NotNull` |
| `otherFormDoesNotInheritProfileFormAllowlist` | `@InitBinder("profileForm")` does not apply to the `otherForm` object name |
| `jsonUsesJacksonNotFormPropertyBinding` | `@RequestBody` JSON is not protected by the form-property allowlist/editor |
| `isoDateIsNotTheFormFormatterPattern` | The local formatter currently requires `dd/MM/uuuu` instead of ISO |

The JSON error output in the demo is **constructed by the controller itself** using `ResponseEntity`; Spring does not return `"fields"` or `"suppressed"` fields by default for every application. In a real application, use a consistent error schema and expose only the necessary information.

## 10. Testing with curl

Start the app:

```bash
mvn spring-boot:run
```

### 10.1. Valid Form with a Disallowed Field

```bash
curl -i -X POST \
  http://localhost:8080/profiles/form \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=  Linh  ' \
  --data-urlencode 'email=linh@example.com' \
  --data-urlencode 'appointmentDate=31/12/2026' \
  --data-urlencode 'admin=true'
```

Expected HTTP **200**, with a body containing the key values:

```json
{
  "displayName": "Linh",
  "email": "linh@example.com",
  "appointmentDate": "2026-12-31",
  "admin": false,
  "suppressed": ["admin"]
}
```

JSON properties are not required to be printed in the exact order shown above. `admin` remains `false` even though the form sent `true` because `setAllowedFields` does not allow binding that property.

### 10.2. Form Failing Validator

```bash
curl -i -X POST \
  http://localhost:8080/profiles/form \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=blocked' \
  --data-urlencode 'email=linh@example.com' \
  --data-urlencode 'appointmentDate=31/12/2026'
```

Expected HTTP **400**, with a body like:

```json
{
  "status": "invalid",
  "fields": ["displayName"],
  "suppressed": []
}
```

This is a **custom Spring Validator** error, not a conversion error. Changing the `appointmentDate` input to `31/99/2026` will produce a binding error on the date field.

### 10.3. JSON with the Same Field Names

```bash
curl -i -X POST \
  http://localhost:8080/profiles/json \
  -H 'Content-Type: application/json' \
  -d '{"displayName":"  Linh  ","email":"linh@example.com","appointmentDate":"2026-12-31","admin":true}'
```

Expected HTTP **200**; the output keeps spaces in `displayName` and has `admin=true`. Jackson reads JSON and calls setters/constructors according to the message converter's mechanism, without enforcing `WebDataBinder`'s **form property-binding whitelist**.

**Security implication:** If clients must not be allowed to set `admin`, you must also prevent it at the **JSON DTO/API contract/authorization** level. `@InitBinder` is not a universal mechanism controlling all ways data is deserialized into Java.

## 11. Distinguishing `@ModelAttribute` from `@RequestBody`

### 11.1. `@ModelAttribute`: The Binder's Primary Territory

`@ModelAttribute` is typically used for query/form fields (and request data that can be bound into properties). Spring creates/prepares the command object, binds values by field name, and can validate it.

```java
@PostMapping("/form")
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult errors) {
    // ...
}
```

In this case, `@InitBinder("profileForm")` is used to configure the corresponding binder. `setAllowedFields`, `StringTrimmerEditor`, `Formatter`, and `addValidators` can affect the exact phases handled by the binder.

### 11.2. `@RequestBody`: `HttpMessageConverter` (Usually Jackson)

```java
@PostMapping("/json")
public ResponseEntity<?> submit(
        @Valid @RequestBody ProfileDto body) {
    // ...
}
```

With `Content-Type: application/json`, Spring uses `HttpMessageConverter` to deserialize the body into an object. Jackson decides how to map JSON fields/constructors/setters. `WebDataBinder#setAllowedFields` **does not block Jackson** from setting fields, and custom `PropertyEditor`/`Formatter` instances used for form binding do not replace the JSON parser.

**Important nuance:** Spring MVC **may still create a WebDataBinder for the validation step** of `@RequestBody` after the argument has been created by the message converter. Therefore, you should not claim "`@InitBinder` is never called with `@RequestBody`." The accurate statement is: **property-binding configuration in `@InitBinder` does not replace Jackson's JSON deserialization mechanism**. Validators added to the binder can participate when the request argument is validated according to the matching configuration and object name.

If you want to forbid a JSON property:
- Use a separate input DTO that does not contain that property.
- Consider Jackson policies such as `@JsonIgnore` / deserialization configuration where appropriate.
- Enforce authorization/business rules in the service layer.
- Do not rely solely on `WebDataBinder#setAllowedFields`.

### 11.3. `@RequestParam` and Simple-Value Conversion

`@RequestParam("count") int count` also requires type conversion from an HTTP string. Spring MVC's conversion/binder mechanism can support customization in the corresponding argument resolvers. However, `@InitBinder("profileForm")` for a form **should not** be treated as a formatting rule applying to all scalar parameters: object names and resolution paths may differ.

If you need a parsing rule for a type application-wide, `WebMvcConfigurer#addFormatters`/`FormattingConversionService` is usually clearer.

## 12. `BindingResult`: Three Types of Issues Easily Conflated

A `BindingResult` can reflect different situations:

| Observation | Meaning | Default `hasErrors()`? |
| --- | --- | --- |
| Client sends `"31/99/2026"` for `LocalDate` | Conversion/type mismatch error | Usually **yes** |
| `@NotBlank` detects empty displayName | Jakarta Bean Validation failure | **Yes** when validation is triggered |
| Custom `ProfileFormValidator` calls `rejectValue` | Spring Validator failure | **Yes** |
| Client sends `admin=true` but field is not in allowlist | Field suppressed from property binding | Not necessarily |
| Client sends extra field not present on DTO | Unknown field may be ignored or flagged depending on config | Not always a validation error |
| Binder `setRequiredFields(...)` detects missing field | Binding required-field error | Possibly yes |

When you want to **reject requests that contain suppressed fields**, you can define your own policy:

```java
if (errors.getSuppressedFields().length > 0) {
    return ResponseEntity.badRequest().body(
            Map.of("error", "unexpected.fields"));
}
```

This snippet is an **illustrative variant**. Do not paste it as-is into `submitForm()` in the section 9 project if you want the `allowedFieldsTrimDateAndSuppressAdmin` test to keep receiving HTTP 200. In practice, returning 400 when suppressed fields are present is often a sensible defensive choice when an API allows only a strictly defined set of fields.

### 12.1. Reading Field Errors

```java
for (var error : errors.getFieldErrors()) {
    String field = error.getField();
    String code = error.getCode();
    String message = error.getDefaultMessage();
}
```

You can map them into a structured error list:
- `field`: property name.
- `code`: e.g., `NotBlank`, `typeMismatch`, or a custom code.
- `message`: the message after interpolation/localization.

Do not return `getRejectedValue()` directly to the client if the data may be sensitive, and do not treat error messages as stable IDs for the frontend. API responses should have clear error codes.

### 12.2. `BindingResult` Position Is Part of the Handler Signature

Correct:

```java
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult errors) {
    // ...
}
```

Incorrect if you expect to capture form errors:

```java
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        @RequestParam String mode,
        BindingResult errors) {
    // BindingResult is no longer immediately after form.
}
```

`BindingResult`/`Errors` usually must sit **immediately after** the bound/validated argument it describes. If you omit `BindingResult` in the proper position and the form is invalid, Spring MVC may throw `MethodArgumentNotValidException`; with direct constraints on the method, the exception type may be `HandlerMethodValidationException` depending on the signature.

## 13. Local Validators Are Not the Same as `@Validated` via AOP

There are three distinct mechanisms:

| Mechanism | When Does It Run? | Target Involved |
| --- | --- | --- |
| `@InitBinder` and `binder.addValidators(...)` | When MVC prepares the binder; validators run if the corresponding validation step is triggered | Command object / request argument |
| `@Valid @ModelAttribute` | When MVC binds and validates the request object | DTO fields, custom validators |
| `@Service @Validated` via `MethodValidationPostProcessor` | When a method invocation passes through a Spring AOP proxy | Method parameters / return value |

Putting `@Validated` on a service **does not replace** controller `@InitBinder` configuration. Conversely, `@InitBinder` is not an AOP advisor and does not intercept method calls outside Spring MVC.

In Spring Framework 6.1+ controllers, direct constraints on handler method parameters can also trigger built-in **method validation**, producing `HandlerMethodValidationException`. `@Valid` on a single DTO argument is not itself a direct constraint. If you only need validation groups for a form, use `@Validated(Group.class) @ModelAttribute(...)` on the appropriate argument; there is no need to place class-level `@Validated` on the entire controller just to select a group.

## 14. Other `WebDataBinder` APIs and Their Effects

### 14.1. `setRequiredFields`

```java
@InitBinder("profileForm")
void init(WebDataBinder binder) {
    binder.setRequiredFields("displayName", "email");
}
```

These fields are declared **required at the binding level**. This can produce binding errors for missing fields. Do not equate this with `@NotBlank`:
- `setRequiredFields` concerns presence in the binding data.
- `@NotBlank` checks the String value after binding/normalization and also rejects whitespace-only values.
- Business contracts might require both, though many projects choose Bean Validation for reusability and clear expression.

This snippet is a standalone illustration; the main project in section 9 does **not** use `setRequiredFields` so learners can clearly observe `@NotNull`/`@NotBlank`.

### 14.2. `setAutoGrowNestedPaths` and Collection Limits

```java
binder.setAutoGrowNestedPaths(false);
binder.setAutoGrowCollectionLimit(128);
```

These APIs control the binder's ability to automatically expand object graphs or collections when property paths like `addresses[100]` are bound. Appropriate limits help prevent requests from intentionally creating very large graphs/collections. However, changing defaults can break binding for valid forms that use nested paths, so test carefully and consult the specific version's documentation.

Do not treat collection limits as a complete security measure: you still need HTTP request size limits, max parameter counts, proper DTO design, and authorization.

### 14.3. `setIgnoreUnknownFields` and `setIgnoreInvalidFields`

```java
binder.setIgnoreUnknownFields(false);
binder.setIgnoreInvalidFields(false);
```

These two mechanisms relate to:
- Fields that **do not exist** on the object.
- Field paths that exist by name but whose target nested path cannot be accessed/initialized.

They do not replace `setAllowedFields`. A field **suppressed by policy** is not the same as an unknown field; suppressed fields are tracked via `BindingResult.getSuppressedFields()`. Only change these flags if you understand their impact on forms, nested properties, and exception/error handling.

### 14.4. `setValidator`, `addValidators`, `replaceValidators`

`setValidator(...)` or `replaceValidators(...)` can replace the validator configuration depending on the overload/version; `addValidators(...)` only **adds** validators. For controllers that need to extend rules, `addValidators` usually preserves Spring Boot's Jakarta provider if it is registered by default. Do not carelessly call `replaceValidators` or discard global Bean Validation when your project needs `@NotBlank`, `@Email`, and `@Valid`.

When adding a custom validator, check `supports()` and test that **both custom and Jakarta constraints** execute on the target object.

## 15. Common Mistakes When Using `@InitBinder`

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Thinking `@InitBinder` is an endpoint | Method does not receive requests | Endpoints must use `@GetMapping`/`@PostMapping`, etc. |
| Using `@InitBinder("user")` with `@ModelAttribute("profileForm")` | Configuration does not apply to the intended binder | Match the exact object name |
| Placing unrestricted `@InitBinder` on a controller with multiple forms | Allowlist or formatter may affect other DTOs | Scope by object name |
| Binding a JPA entity directly from a form | Risk of over-posting sensitive properties | Use a dedicated request DTO and allowlist |
| Using only `setDisallowedFields("admin")` | Easy to miss new fields or name variants | Prefer explicit `setAllowedFields` |
| Thinking `setAllowedFields` also blocks Jackson JSON | JSON message converter does not use setter property binder | Separate DTO/Jackson config/authorization |
| Assuming suppressed fields automatically return 400 | Suppression is not necessarily a binding error | Check `getSuppressedFields()` and decide policy |
| Registering `StringTrimmerEditor` too broadly | May alter passwords/tokens/emails unintentionally | Configure per appropriate field |
| Setting a Formatter for `LocalDate` when the request is JSON | Jackson does not use the binder's form formatter | Use Jackson date format or separate DTO |
| Adding a custom validator but forgetting `@Valid`/`@Validated` | Validation may not be triggered | Place the annotation on the request argument |
| `supports()` returns `false` for the DTO | Validator incompatible with type, may fail configuration | Test the exact target type |
| Using `@NotBlank` on `LocalDate` or `int` | Incompatible constraint type | Use `@NotNull`, `@Min`, `@Future`, etc. |
| Placing `BindingResult` not immediately after the form | Handler fails to receive binding errors properly | Place it immediately after `@ModelAttribute` |
| Using an editor with mutable static state | Can cause bugs under concurrent requests | Each binder/formatter should be stateless or thread-safe |
| Enabling `setDeclarativeBinding(true)` while expecting all fields to setter-bind | Property binding is restricted unless allowlisted | Design constructor binding or explicit `allowedFields` |
| Thinking allowlist also protects constructor binding | They are two separate binding channels | Design the DTO constructor with only public fields |
| Relying on `@InitBinder` to authorize role/admin changes | Binder is only an input filter, not authorization | Enforce permissions in service/security layers |

## 16. Debugging a Form That Does Not Bind or Validate as Expected

Investigation sequence for integration tests:

1. **Confirm the stack:** Are you using Spring MVC Servlet or WebFlux?
2. **Confirm the selected handler:** Are the URL, HTTP method, and `Content-Type` correct?
3. **Confirm argument annotations:** Is there `@ModelAttribute("profileForm")` or a request argument handled by a binder?
4. **Confirm object name:** Does `@InitBinder("profileForm")` match the `@ModelAttribute` name? Even a single character difference will not match.
5. **Confirm form field names:** Does `displayName` in HTML match the setter `setDisplayName`?
6. **Confirm allowlist:** Was the field suppressed by `setAllowedFields`? Check `BindingResult.getSuppressedFields()`.
7. **Confirm editor/formatter:** Does the `dd/MM/uuuu` format match the request? Is another format annotation taking precedence?
8. **Confirm validators:** Is there a Jakarta provider and `@Valid`/`@Validated`? Does custom `supports()` match?
9. **Confirm `BindingResult`:** Is it immediately after the argument being validated? Which bind errors and field errors exist?
10. **Confirm conversion exceptions:** `typeMismatch` differs from `NotBlank`; do not lump every 400 into a single cause.
11. **Check body format:** JSON goes through Jackson, not form property binding.
12. **Check shared advice:** Is any `@ControllerAdvice` modifying binders across all controllers?
13. **Check DTO design:** Is constructor binding accepting fields that the setter allowlist does not control?
14. **Check security:** Is a client trying to pass permission/admin/ID fields that the controller should not trust?
15. **Check test path:** `MockMvc` goes through the framework, unlike calling a handler method directly in Java.

Especially on a successful request, still verify whether invalid or disallowed fields were ignored—HTTP 200 does not prove every input field was used.

## 17. Practice Exercises

1. Change `@InitBinder("profileForm")` to `@InitBinder("otherForm")`. Predict which tests fail: trimming, date parsing, allowlist, custom validator, and scope.
2. Remove `setAllowedFields` and send `admin=true` to `/profiles/form`. Observe the response to explain the over-posting risk.
3. Keep the allowlist but add `unknownFlag=true`. Use `getSuppressedFields()` to see which field is blocked and how it differs from an unknown field.
4. Change `StringTrimmerEditor(true)` to `StringTrimmerEditor(false)` and send `displayName="  "`. Why does `@NotBlank` still reject it while the value inside the DTO differs?
5. Change the pattern to `yyyy-MM-dd` and rerun the date test; explain why `31/12/2026` is no longer accepted.
6. Temporarily remove `@Valid` on `@ModelAttribute("profileForm")` and send `displayName=blocked`. Check whether the custom validator still runs automatically.
7. Temporarily change `ProfileFormValidator.supports` to support another class. Observe the effect on validator registration and why the contract must be implemented properly.
8. Change the policy: return HTTP 400 if `getSuppressedFields().length > 0`; update tests to expect the new status and error code.
9. Write an immutable record DTO allowing only `displayName` and `email`. Enable `setDeclarativeBinding(true)` and compare it with setter binding on a mutable DTO.
10. Move `@InitBinder` to `@ControllerAdvice(assignableTypes=ProfileController.class)` and rerun tests; observe the scope of application.
11. Place `@DateTimeFormat(pattern="dd/MM/uuuu")` on the field, remove the custom formatter from the binder, and verify that conversion still succeeds.
12. Add a JSON endpoint with `@Valid @RequestBody ProfileForm`; observe how validation runs while the allowlist does not block Jackson.
13. Register the formatter globally via `WebMvcConfigurer#addFormatters`, then remove the controller-level formatter; analyze the trade-offs.
14. Add a nested field `contact.email` and design a narrow allowlist so clients can edit only `email`, not other properties of `contact`.

**Key takeaway:** `@InitBinder` is a **configuration hook for `WebDataBinder`** scoped by controller or object name, helping control how form/query data is bound, converted, and validated. It does not replace `@Valid`, `BindingResult`, Jackson JSON deserialization, DTO design, or authorization. Before using `@InitBinder`, clearly identify **which object is being bound**, **which binding channel** is active, and **which fields** are allowed from the client.

## 18. Official Documentation Sources

- [Spring Framework 6.2 — @InitBinder in Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — @ModelAttribute argument binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — @RequestBody and HttpMessageConverter](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — Validation config and custom @InitBinder Validator](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html)
- [Spring Framework 6.2 — DataBinder API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — WebDataBinder API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/WebDataBinder.html)
- [Spring Framework 6.2 — Spring MVC validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — @ControllerAdvice scope](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html)
- [Spring Boot 3.5 — Testing MVC with MockMvc](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Jakarta Validation 3.0 specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)