# Registering Binders with @InitBinder in Spring WebFlux

## 1. Goal: Tailoring Binding to the Right Form and Controller

In Spring WebFlux, annotation-based handlers frequently receive data from query strings, URL-encoded forms, or multipart payloads via `@ModelAttribute`. The framework instantiates or retrieves the target object, extracts data from `ServerWebExchange`, and uses `WebExchangeDataBinder` to convert types, populate properties, record binding errors, and coordinate with validation.

Yet each form has its own rules:
- Allow users to edit only certain properties, preventing assignment to `admin` or `approved`.
- Require an event date in one form to follow `dd/MM/yyyy`.
- Prevent an input list from auto-growing to thousands of elements.
- Beyond `@NotBlank` and `@Min`, validate a business rule via a Spring `Validator`.
- Share common binding rules across controllers without duplicating the same setup in every endpoint.

**`@InitBinder` is the extension hook for configuring a `WebDataBinder` right before the binder is used for a request argument/model attribute.** It is not an annotation marking a handler URL; an `@InitBinder` method typically accepts `WebDataBinder`, returns `void`, and is invoked by the framework to register editors, formatters, validators, or binding allowlists.

Short example:

~~~java
@RestController
class SignupController {

    @InitBinder("signupForm")
    void configureSignup(WebDataBinder binder) {
        binder.setAllowedFields("fullName", "age", "eventDate");
        binder.setAutoGrowCollectionLimit(5);
    }

    @PostMapping("/signups")
    String signup(@Valid @ModelAttribute("signupForm") SignupForm form,
                  BindingResult errors) {
        return errors.hasErrors() ? "invalid" : "accepted";
    }
}
~~~

The snippet above is **illustrative** and requires `SignupForm`, imports, and other components to run. Naming `"signupForm"` on both `@InitBinder` and `@ModelAttribute` is intentional: the binder receives that local configuration only when the object name matches. For a DTO with a `setAdmin(boolean)` setter, a request field `admin=true` **is not property-bound** because it is not in `allowedFields`.

This lesson focuses on **WebFlux 6.1/6.2**, and the complete example uses **Spring Boot 3.5.7, Spring Framework 6.2, Java 17**. Do not confuse it with Servlet MVC's `@InitBinder` even though the APIs look similar.

## 2. Processing Flow: From `ServerWebExchange` to `@InitBinder` to Handler

~~~text
Request arrives at WebFlux
   |
   v
DispatcherHandler -> RequestMappingHandlerAdapter
   |
   v
Locate controller method, resolve @ModelAttribute parameter
   |
   +-- Find/create target object (constructor binding if applicable)
   |
   +-- Create WebExchangeDataBinder for model attribute
   |      |
   |      +-- @ControllerAdvice @InitBinder (applied first)
   |      |
   |      +-- @Controller @InitBinder (applied after, can restrict by name)
   |      |
   |      +-- allowedFields, formatter/editor, validators, limits
   |
   +-- Gather query/form/multipart and applicable additional sources
   |
   +-- Property binding + conversion + BindingResult
   |
   +-- @Valid / @Validated: run validation if requested
   |
   +-- BindingResult immediately after object -> handler handles errors
   |   None -> typically WebExchangeBindException if object is invalid
   |
   v
Invoke controller method, return value/Mono/HTTP response
~~~

This diagram is **conceptual**. For immutable objects, Spring can perform constructor binding during target instantiation; `allowedFields` applies to **property binding** and does not automatically turn every constructor parameter into a blocked list. If the method has direct Bean Validation constraints on parameters or return value, Spring WebFlux 6.1+ may switch to *method validation*, raising a different exception type. Those details are distinguished in section 9.

### Component roles

| Component | Role |
| --- | --- |
| `ServerWebExchange` | Context of an HTTP request/response; holds query, `getFormData()`, `getMultipartData()`, attributes, session |
| `WebExchangeDataBinder` | Binder that extracts data from the exchange via a reactive contract |
| `WebDataBinder` | Superclass/parameter type commonly used in `@InitBinder`, providing APIs to register editors/formatters/validators |
| `DataBinder` | Foundation for property/constructor binding, conversions, allowlists, and `BindingResult` |
| `@ModelAttribute` | Declares a handler argument as a form/model object to bind |
| `@InitBinder` | Method that configures the binder, not a handler directly accepting request bodies as business data |
| `@ControllerAdvice` | Enables reusing `@InitBinder` across multiple controllers, with optional scope narrowing |
| `@Valid` / `@Validated` | Requests post-binding constraint validation via the appropriate integration |
| `BindingResult` | Holds binding/conversion/validation errors for the corresponding model attribute |

**Common misconception:** `@InitBinder` does not require you to call `binder.bind(exchange)` yourself. For an annotated controller, Spring manages that step. Only when building a custom argument resolver do you manually instantiate `WebExchangeDataBinder` and compose the publisher returned by `bind(exchange)`.

## 3. Declaring `@InitBinder`: Syntax, Scope, and Constraints

### 3.1. Local binder on a controller

~~~java
@Controller
class FormController {

    @InitBinder
    void initAll(WebDataBinder binder) {
        binder.setAutoGrowCollectionLimit(16);
    }

    // Handler methods...
}
~~~

An unnamed `@InitBinder` applies to all matching binders within this controller's scope. When targeting a single model attribute, pass its name:

~~~java
@InitBinder("signupForm")
void initSignup(WebDataBinder binder) {
    binder.setAllowedFields("fullName", "age", "eventDate");
}
~~~

The `value` name is the **command/form attribute or request parameter** name for which the binder is used. With `@ModelAttribute("signupForm")`, the name matches explicitly; **do not rely on implicit Java parameter names** when multiple DTOs share types or have varying names.

Multiple names can be specified:

~~~java
@InitBinder({"signupForm", "profileForm"})
void initTheseForms(WebDataBinder binder) {
    binder.setAutoGrowCollectionLimit(16);
}
~~~

These are **independent illustrative options**; do not paste all of them into the same controller and accidentally overwrite binder settings. In real code, each `@InitBinder` should have clear responsibility and consistent target names.

### 3.2. Keep `@InitBinder` signatures simple and synchronous

An `@InitBinder` method normally takes `WebDataBinder` and returns `void`:

~~~java
@InitBinder("signupForm")
void configureBinder(WebDataBinder binder) {
    binder.setAllowedFields("fullName", "age", "eventDate", "topics[*]");
}
~~~

Do not declare `Mono<Void>` as the return type of `@InitBinder` expecting Spring to subscribe to complete configuration. This is a **synchronous registration/configuration hook**; reactivity lies in how the framework reads HTTP data, runs the binder, and handles the handler's return type. When async logic like database queries is needed, run it in a service/reactive pipeline—never put blocking I/O inside `@InitBinder`.

Per the `@InitBinder` contract, the method has no return value and must not accept command/form model objects or `BindingResult` as arguments. Request context parameter types may be supported depending on handler argument resolvers, but for maintainability stick to `WebDataBinder` and request-dependent config only where proven necessary; avoid relying on Servlet-stack types like `HttpServletRequest` in WebFlux.

### 3.3. Registering in `@ControllerAdvice`

~~~java
@ControllerAdvice
class SharedBindingAdvice {

    @InitBinder
    void common(WebDataBinder binder) {
        binder.setAutoGrowCollectionLimit(8);
    }
}
~~~

This configuration can apply across many controllers. Spring WebFlux runs `@InitBinder` methods from **`@ControllerAdvice` first**, followed by **local** binder methods declared inside the controller. If multiple methods write the same property, that execution order affects the outcome; do not rely on "last writer wins" as a policy management strategy.

Narrowing advice scope:

~~~java
@ControllerAdvice(assignableTypes = SignupController.class)
class SignupOnlyAdvice {
    @InitBinder
    void common(WebDataBinder binder) {
        binder.setAutoGrowCollectionLimit(8);
    }
}
~~~

`assignableTypes` restricts the advice to the specified controller types; you can also choose `basePackages`, `basePackageClasses`, or `annotations` per your architecture. `@ControllerAdvice` selectors define **controller scope**, whereas `@InitBinder("signupForm")` defines **object-name scope**. The two concepts are orthogonal.

### 3.4. Per-request binder, validators, and state

Spring creates a binder per binding operation, so configuring editors/formatters on a binder does not require sharing a mutable `SimpleDateFormat` across threads. However, **`@ControllerAdvice`/controller instances are typically singletons**, so never store per-request state in fields of an advice class.

Reusable validators can be singleton beans if they are genuinely stateless and thread-safe; the runnable example below uses a stateless validator class.

## 4. Essential APIs on `WebDataBinder`

| API | Effect | Important Notes |
| --- | --- | --- |
| `setAllowedFields("name", "items[*].code")` | Whitelists property binding by path pattern | Case-sensitive; prefer allowlists |
| `setDisallowedFields(...)` | Blocks specific fields | Easy to miss new DTO properties; not a substitute for allowlists |
| `setDeclarativeBinding(true)` | Constructor binding only by default, plus property binding if `allowedFields` is set | Does not make constructor args authorized automatically |
| `setAutoGrowCollectionLimit(int)` | Limits array/list auto-growth | Not an HTTP size limit or Map entry quota |
| `setAutoGrowNestedPaths(boolean)` | Controls auto-growing nested properties | Applies to property binding, not universally to constructor binding |
| `registerCustomEditor(type, editor)` | Uses a `PropertyEditor` during value conversion | Editors are per-binder; avoid sharing mutable instances |
| `addCustomFormatter(formatter)` | Adds a `Formatter` with parse/print | Can be scoped to specific fields when needed |
| `addValidators(Validator...)` | Appends Spring validators | Avoids accidentally replacing the entire global validator |
| `setValidator(validator)` | Sets the validator | Can overwrite another validator; weigh carefully before using |
| `setRequiredFields(...)` | Marks fields that must appear in property values | Distinct from `@NotNull` on the bound model |
| `getBindingResult()` | Binding/validation results | Provides `FieldError`, `ObjectError`, `getSuppressedFields()` |

### `setAllowedFields` and property path names

~~~text
fullName
age
eventDate
topics[0]
topics[1]
addresses[0].city
settings[timezone]
~~~

To permit specific fields without exposing the whole object graph, use:

~~~java
binder.setAllowedFields(
    "fullName", "age", "eventDate", "topics[*]"
);
~~~

The `*` pattern is Spring's wildcard for field names; `topics[*]` matches indices like `topics[0]`. For nested forms you can write `addresses[*].city`, and for Maps `settings[timezone]`. Overly broad patterns like `*`, `addresses*`, or `settings*` can expose unintended properties.

Fields rejected by the allowlist are recorded in `BindingResult#getSuppressedFields()`, **not necessarily as `FieldError` entries**. If a request sends `admin=true` while the controller only allows the fields above, `admin` is suppressed without automatically making `errors.hasErrors()` return `true`.

### `setRequiredFields` vs `@NotNull`

~~~java
binder.setRequiredFields("fullName");
~~~

This checks the presence/availability of the field in **property values** during binding. It does not replace `@NotBlank`, since a field can be present yet hold whitespace. `@NotNull` is a constraint on the object after conversion/validation, and has different semantics for nested data. Avoid duplicating binder required rules and overlapping Jakarta constraints unintentionally; responses may emit multiple differing error codes.

### `setDeclarativeBinding(true)`

~~~java
@InitBinder
void secureBinding(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
~~~

Since Spring Framework 6.1+, this setting ensures **constructor binding** continues to work while **property binding** is used only if `allowedFields` is explicitly configured. It is a strong option for restricting setter/property binding, though not "automatic security" if a constructor accepts parameters clients should not control. Designing small request DTOs, matching constructor contracts, and checking authorization remain essential.

## 5. Formatter, PropertyEditor, and Validator: What to Register?

### 5.1. `PropertyEditor`: simple and single-type focused

For input `eventDate=25/12/2026`, instead of the default ISO `2026-12-25` converter format, you can register an editor for `LocalDate`:

~~~java
private static final DateTimeFormatter DATE =
        DateTimeFormatter.ofPattern("dd/MM/uuuu")
                .withResolverStyle(ResolverStyle.STRICT);

@InitBinder("signupForm")
void init(WebDataBinder binder) {
    binder.registerCustomEditor(LocalDate.class,
            new PropertyEditorSupport() {
                @Override
                public void setAsText(String text) {
                    setValue(LocalDate.parse(text, DATE));
                }

                @Override
                public String getAsText() {
                    LocalDate value = (LocalDate) getValue();
                    return value == null ? "" : value.format(DATE);
                }
            });
}
~~~

The snippet above is **not a standalone class**: import `java.beans.PropertyEditorSupport`, `java.time.LocalDate`, `java.time.format.DateTimeFormatter`/`ResolverStyle`, and `WebDataBinder`, placed inside a controller. `DateTimeFormatter` is immutable and shareable; `PropertyEditorSupport` is mutable, so create a fresh instance per binder rather than keeping a global static instance.

With `DateTimeFormatter.ofPattern("dd/MM/uuuu")` and `ResolverStyle.STRICT`, `25/12/2026` parses while `31/02/2026` is rejected. When conversion fails in a form, Spring records a type mismatch error in `BindingResult`; without a `BindingResult` next to the model attribute, the error causes WebFlux to throw `WebExchangeBindException`.

### 5.2. `Formatter<T>`: idiomatic solution for parsing and printing

~~~java
// Illustrative method snippet, assuming FORMAT and imports exist.
@InitBinder("signupForm")
void initFormatter(WebDataBinder binder) {
    binder.addCustomFormatter(new Formatter<LocalDate>() {
        @Override
        public LocalDate parse(String text, Locale locale) {
            return LocalDate.parse(text, FORMAT);
        }

        @Override
        public String print(LocalDate value, Locale locale) {
            return FORMAT.format(value);
        }
    });
}
~~~

`Formatter<T>` provides `parse(String, Locale)` and `print(T, Locale)`. Use it when you want consistent representation across inputs and rendered forms. When multiple controllers share ISO date/time formats, prefer global registration via `WebFluxConfigurer#addFormatters(FormatterRegistry)` or `@DateTimeFormat` on fields if simple enough, rather than copying an anonymous formatter into every controller.

Use **one** of the editor or formatter approaches for the same type and scope to avoid competing conversion rules. The runnable example below uses `PropertyEditorSupport` so date-parsing behavior is clearly visible.

### 5.3. Spring `Validator` and Jakarta Bean Validation

`@InitBinder` can also attach a Spring Validator:

~~~java
@InitBinder("signupForm")
void initValidator(WebDataBinder binder) {
    binder.addValidators(new SignupPolicyValidator());
}
~~~

This is an **illustrative snippet** without constructing the validator class. The `org.springframework.validation.Validator` interface has `supports(Class<?>)` and `validate(Object, Errors)`. `@Valid` triggers applicable validators per the controller lifecycle and classpath Bean Validation provider. Custom validations from `addValidators` run **alongside** Jakarta `@NotBlank` and `@Min` as long as the global validator is not replaced.

Do not confuse `binder.addValidators(...)` with `binder.setValidator(...)`: adding a validator merges deliberately; setting one can discard the out-of-the-box Jakarta validation. Validators must restrict supported target types accurately via `supports(...)`.

### 5.4. When to use global `WebFluxConfigurer`?

When all controllers need the same converter or formatter:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        // Register shared Formatters/Converters.
    }
}
~~~

This illustrative snippet needs imports for `Configuration`, `WebFluxConfigurer`, and `FormatterRegistry`. In an auto-configured Spring Boot application, `@EnableWebFlux` is unnecessary just to register a formatter. The strength of a global `ConversionService` is consistent logic across the app; the strength of `@InitBinder` is controller/attribute-scoped customization. Both should complement each other without uncontrolled overrides.

## 6. Runnable Example: WebFlux Registration Form with Local and Global Binders

The example uses Spring Boot **3.5.7**, Java **17**, Maven, and only `spring-boot-starter-webflux` to prevent Web MVC from being chosen if a Servlet starter were added. Tests use `WebTestClient`, not `MockMvc`.

### 6.1. Project structure

~~~text
pom.xml
src/main/java/com/example/binder/
  BinderApplication.java
  SignupForm.java
  SignupPolicyValidator.java
  SignupBindingAdvice.java
  SignupController.java
src/test/java/com/example/binder/
  SignupControllerTest.java
  SignupBinderTest.java
~~~

### 6.2. `pom.xml`

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
    <artifactId>webflux-initbinder-demo</artifactId>
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

`spring-boot-starter-validation` brings a Jakarta Bean Validation implementation onto the classpath; `spring-boot-starter-test` brings JUnit 5 and WebFlux test infrastructure. There is no database, security dependency, or persistence layer in this demo.

### 6.3. Main class

~~~java
// src/main/java/com/example/binder/BinderApplication.java
package com.example.binder;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BinderApplication {
    public static void main(String[] args) {
        SpringApplication.run(BinderApplication.class, args);
    }
}
~~~

### 6.4. `SignupForm`: dedicated to web input

~~~java
// src/main/java/com/example/binder/SignupForm.java
package com.example.binder;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

public class SignupForm {

    @NotBlank(message = "Full name must not be blank")
    private String fullName;

    @NotNull(message = "Age is required")
    @Min(value = 18, message = "Age must be at least 18")
    private Integer age;

    @NotNull(message = "Event date is required")
    private LocalDate eventDate;

    @Size(max = 3, message = "At most 3 topics")
    private List<@NotBlank String> topics = new ArrayList<>();

    // Only to demonstrate over-posting; do not put in real public DTOs.
    private boolean admin;

    public SignupForm() {}

    public String getFullName() { return fullName; }
    public void setFullName(String fullName) { this.fullName = fullName; }

    public Integer getAge() { return age; }
    public void setAge(Integer age) { this.age = age; }

    public LocalDate getEventDate() { return eventDate; }
    public void setEventDate(LocalDate eventDate) {
        this.eventDate = eventDate;
    }

    public List<String> getTopics() { return topics; }
    public void setTopics(List<String> topics) { this.topics = topics; }

    public boolean isAdmin() { return admin; }
    public void setAdmin(boolean admin) { this.admin = admin; }
}
~~~

The bean has a default constructor and getters/setters to illustrate **property binding**. It receives the object name `signupForm` specified by `@ModelAttribute("signupForm")`; the class name does not need to match the variable name in the handler.

Constraints:
- `@NotBlank` on `fullName` rejects `null`, empty, and whitespace-only values.
- `@NotNull`/`@Min(18)` on `age` enforce presence and minimum value.
- `@NotNull` on `eventDate` requires a valid date after conversion.
- `@Size(max=3)` caps list length, and type-use `@NotBlank` validates each element.
- `admin` is an example of a sensitive property clients **must not bind**. In real production code, remove this property from request DTOs and enforce authorization on the server.

### 6.5. Custom Spring Validator

~~~java
// src/main/java/com/example/binder/SignupPolicyValidator.java
package com.example.binder;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class SignupPolicyValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return SignupForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;
        if ("blocked".equalsIgnoreCase(form.getFullName())) {
            errors.rejectValue("fullName", "reserved.name",
                    "This name is not allowed");
        }
    }
}
~~~

The validator above is stateless: no external API calls, no side effects. With `fullName=blocked`, Jakarta's `@NotBlank` considers the string syntactically valid, while the custom rule `SignupPolicyValidator` records a `FieldError` with code `reserved.name`. This clearly illustrates **two complementary validation layers**.

`supports(Class<?>)` ensures the validator accepts only `SignupForm` and subclasses; never attach a validator that does not support the target to a global binder. When a custom business rule needs async database lookups, never make blocking repository calls inside synchronous `validate`; put that rule in a reactive service pipeline after binding.

### 6.6. Global `@ControllerAdvice`: trim strings

~~~java
// src/main/java/com/example/binder/SignupBindingAdvice.java
package com.example.binder;

import org.springframework.beans.propertyeditors.StringTrimmerEditor;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.InitBinder;

@ControllerAdvice(assignableTypes = SignupController.class)
public class SignupBindingAdvice {

    @InitBinder
    void trimStrings(WebDataBinder binder) {
        binder.registerCustomEditor(
                String.class, new StringTrimmerEditor(true));
    }
}
~~~

The advice targets only `SignupController` via `assignableTypes`; inside it, `@InitBinder` has no object name restriction so it applies to matching binders for that controller. `StringTrimmerEditor(true)` trims leading/trailing whitespace and converts empty-after-trim strings to `null`. For example, `"  Lan  "` becomes `"Lan"`, and `"    "` becomes `null`.

Do not use `StringTrimmerEditor` to alter strings indiscriminately if business rules must preserve whitespace (passwords, signed text, tokens, formatted content). Use it only when input fields genuinely carry that semantics. **Global advice runs before local binder methods** in Spring WebFlux; in this demo, global registers an editor for `String` and local registers one for `LocalDate`, so they do not conflict.

### 6.7. Controller: local `@InitBinder("signupForm")`

~~~java
// src/main/java/com/example/binder/SignupController.java
package com.example.binder;

import jakarta.validation.Valid;
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

import java.beans.PropertyEditorSupport;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/signups")
public class SignupController {

    private static final DateTimeFormatter DATE =
            DateTimeFormatter.ofPattern("dd/MM/uuuu")
                    .withResolverStyle(ResolverStyle.STRICT);

    @InitBinder("signupForm")
    void configureSignupBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "fullName", "age", "eventDate", "topics[*]");
        binder.setAutoGrowCollectionLimit(5);

        binder.registerCustomEditor(
                LocalDate.class, new PropertyEditorSupport() {
                    @Override
                    public void setAsText(String text) {
                        setValue(LocalDate.parse(text, DATE));
                    }

                    @Override
                    public String getAsText() {
                        LocalDate date = (LocalDate) getValue();
                        return date == null ? "" : date.format(DATE);
                    }
                });

        binder.addValidators(new SignupPolicyValidator());
    }

    @PostMapping(consumes =
            MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<ResponseEntity<Map<String, Object>>> register(
            @Valid @ModelAttribute("signupForm") SignupForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            List<String> fields = errors.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .toList();

            Map<String, Object> response =
                    Map.of("invalidFields", fields);
            return Mono.just(ResponseEntity.badRequest().body(response));
        }

        Map<String, Object> response = Map.of(
                "name", form.getFullName(),
                "age", form.getAge(),
                "eventDate", form.getEventDate().toString(),
                "topics", form.getTopics(),
                "admin", form.isAdmin()
        );
        return Mono.just(ResponseEntity.ok(response));
    }

    @PostMapping(path = "/strict", consumes =
            MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<String> registerStrict(
            @Valid @ModelAttribute("signupForm") SignupForm form) {
        return Mono.just("accepted:" + form.getFullName());
    }
}
~~~

**Execution flow of the code above:**
1. Spring WebFlux receives the URL-encoded form, sees `@ModelAttribute("signupForm")`, and instantiates `SignupForm`.
2. `SignupBindingAdvice.trimStrings` registers the `String` editor (advice-scoped).
3. `SignupController.configureSignupBinder` runs for the binder with object name `signupForm`; it registers the allowlist, growth limit, `LocalDate` editor, and custom Spring Validator.
4. The binder assigns allowed fields and performs type conversion. `admin=true` is suppressed because it is outside the allowlist.
5. `@Valid` triggers Bean Validation and registered validators. `BindingResult` holds conversion and constraint errors.
6. In `register`, if errors exist, it returns 400 listing **field names** only. If valid, it returns a JSON summary of the form.
7. In `registerStrict`, there is no `BindingResult` immediately after the model attribute: object binding/validation failures produce `WebExchangeBindException` with HTTP 400 before the method executes.

`Mono.just(...)` here is simply the handler's reactive return type. It does not mean `@InitBinder` runs asynchronously or that `BindingResult` can be read before binding finishes; Spring resolves arguments before invoking the controller body.

### 6.8. HTML form and curl

A simple HTML form sending the right field names:

~~~html
<form action="/signups" method="post">
  <input name="fullName" value="  Lan  ">
  <input name="age" type="number" value="21">
  <input name="eventDate" value="25/12/2026">
  <input name="topics[0]" value="webflux">
  <button type="submit">Sign Up</button>
</form>
~~~

When the browser submits the form, characters like `[`, `]`, and `/` may be URL-encoded. Spring WebFlux receives the logical field name `topics[0]` and value `25/12/2026` after reading/decoding the request.

Run from a terminal supporting `\` line continuation (Linux/macOS/Git Bash):

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -i -X POST http://localhost:8080/signups \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "fullName=  Lan  " \
  --data-urlencode "age=21" \
  --data-urlencode "eventDate=25/12/2026" \
  --data-urlencode "topics[0]=webflux" \
  --data-urlencode "admin=true"
~~~

Expected JSON response, ignoring property order:

~~~json
{
  "name": "Lan",
  "age": 21,
  "eventDate": "2026-12-25",
  "topics": ["webflux"],
  "admin": false
}
~~~

`name` was trimmed by the global advice; `eventDate` was parsed as `dd/MM/uuuu` and printed via `LocalDate#toString()` in ISO format; `topics[0]` was populated by indexed property binding; `admin` stayed false due to the allowlist. That **does not mean** the server performed account authentication/authorization—it only demonstrates blocking unauthorized property binding.

On PowerShell, a single-line `curl.exe` command or PowerShell's line continuation works better than directly copying Unix shell `\` continuations.

## 7. Testing `@InitBinder` with WebTestClient and JUnit

### 7.1. HTTP-level integration tests

~~~java
// src/test/java/com/example/binder/SignupControllerTest.java
package com.example.binder;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@AutoConfigureWebTestClient
@SpringBootTest
class SignupControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void localAndAdviceBindersWorkTogether() {
        client.post()
                .uri("/signups")
                .body(BodyInserters.fromFormData("fullName", "  Lan  ")
                        .with("age", "21")
                        .with("eventDate", "25/12/2026")
                        .with("topics[0]", "webflux")
                        .with("admin", "true"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("Lan")
                .jsonPath("$.age").isEqualTo(21)
                .jsonPath("$.eventDate").isEqualTo("2026-12-25")
                .jsonPath("$.topics[0]").isEqualTo("webflux")
                .jsonPath("$.admin").isEqualTo(false);
    }

    @Test
    void jakartaConstraintsAreApplied() {
        client.post()
                .uri("/signups")
                .body(BodyInserters.fromFormData("fullName", " ")
                        .with("age", "16")
                        .with("eventDate", "25/12/2026"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.invalidFields").isArray()
                .jsonPath("$.invalidFields[0]").isEqualTo("age")
                .jsonPath("$.invalidFields[1]").isEqualTo("fullName");
    }

    @Test
    void customSpringValidatorIsApplied() {
        client.post()
                .uri("/signups")
                .body(BodyInserters.fromFormData("fullName", "blocked")
                        .with("age", "21")
                        .with("eventDate", "25/12/2026"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.invalidFields[0]").isEqualTo("fullName");
    }

    @Test
    void wrongDateFormatIsBindingError() {
        client.post()
                .uri("/signups")
                .body(BodyInserters.fromFormData("fullName", "Lan")
                        .with("age", "21")
                        .with("eventDate", "2026-12-25"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.invalidFields[0]").isEqualTo("eventDate");
    }

    @Test
    void strictHandlerWithoutBindingResultReturns400() {
        client.post()
                .uri("/signups/strict")
                .body(BodyInserters.fromFormData("fullName", " ")
                        .with("age", "16")
                        .with("eventDate", "25/12/2026"))
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

These assertions test **real WebFlux handler behavior**, not merely whether the controller method carries annotations:
- Test 1 verifies that the advice and local `@InitBinder` work together: trimming, custom date parsing, allowlist, indexed List, and blocking `admin`.
- Test 2 verifies Bean Validation (`@NotBlank`/`@Min`). Because the controller explicitly sorts field errors, index 0 is `age` and index 1 is `fullName`.
- Test 3 proves the custom Spring Validator attached via `addValidators` is invoked.
- Test 4 verifies the date editor rejects ISO format in this controller's form; the failure is a binding/conversion error.
- Test 5 verifies that a model attribute without a trailing `BindingResult` takes the framework's error path (400).

Do not assert verbatim error messages or JSON payloads when the framework handles errors automatically; those details vary by locale, message source, and error handler. In tests with `BindingResult`, the response is defined by the controller, so field lists can be asserted safely.

### 7.2. Unit testing binder configuration directly

`@InitBinder` is invoked by Spring when requests arrive at the controller. When you want to verify conversion/allowlist configuration in isolation, you can create a `WebDataBinder` manually and invoke the configuration method (test placed in the same package):

~~~java
// src/test/java/com/example/binder/SignupBinderTest.java
package com.example.binder;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.web.bind.WebDataBinder;

import java.time.LocalDate;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class SignupBinderTest {

    @Test
    void localBinderConfigCanBeVerifiedWithoutHttp() {
        SignupForm form = new SignupForm();
        WebDataBinder binder = new WebDataBinder(form, "signupForm");
        new SignupController().configureSignupBinder(binder);

        binder.bind(new MutablePropertyValues(Map.of(
                "fullName", "blocked",
                "age", "21",
                "eventDate", "25/12/2026",
                "admin", "true"
        )));
        binder.validate();

        assertEquals(LocalDate.of(2026, 12, 25),
                form.getEventDate());
        assertEquals(21, form.getAge());
        assertFalse(form.isAdmin());
        assertArrayEquals(new String[]{"admin"},
                binder.getBindingResult().getSuppressedFields());

        // Custom validator on the local binder, independent of HTTP.
        assertNotNull(
                binder.getBindingResult().getFieldError("fullName"));
    }
}
~~~

This test **does not** invoke `@ControllerAdvice` and does not register a Jakarta Bean Validation provider. It tests only the local binder method, property editors, allowlist, and custom Spring validator. Thus `fullName` stays `"blocked"` and the custom validator records the field error; the test does not depend on the global StringTrimmerEditor.

Run all tests:

~~~bash
mvn test
~~~

**Expected result:** 6 JUnit tests PASS (5 WebTestClient, 1 WebDataBinder unit test) with the dependencies and Spring Boot 3.5.7 specified in this lesson. This states the expected outcome per the documented API/flow, **not an assertion that Maven was executed**. To run a single test class:

~~~bash
mvn -Dtest=SignupControllerTest test
~~~

## 8. Distinguishing `@InitBinder` from `@RequestBody` JSON

This is the most common architectural mistake when using allowlists: developers add `@InitBinder` with `allowedFields` and believe all client input is now filtered. That is **false** for JSON deserialization.

### Form style, with property names

~~~http
POST /signups HTTP/1.1
Content-Type: application/x-www-form-urlencoded

fullName=Lan&age=21&eventDate=25%2F12%2F2026&admin=true
~~~

Spring WebFlux `@ModelAttribute` goes through model binding, where `WebDataBinder#setAllowedFields(...)` can block `admin`.

### JSON style

~~~http
POST /api/signups HTTP/1.1
Content-Type: application/json

{"fullName":"Lan","age":21,"admin":true}
~~~

For an `@Valid @RequestBody SomeInputDto` handler, WebFlux typically uses the JSON `HttpMessageReader`/Jackson to deserialize directly into the object. `@InitBinder` may participate in configuring validation/binders where the framework allows, yet **`setAllowedFields` is not a Jackson JSON property filter**. If the JSON DTO exposes a sensitive setter, clients can still populate it before validation runs.

**Right approach:** input DTOs should contain only fields users are allowed to control; avoid exposing `admin`/`role`/`ownerId`. Configure Jackson annotations when needed, while keeping authorization and domain validation on the server. Never use a form allowlist as a general security mechanism for JSON.

If an endpoint accepts both form data and JSON, design two separate contracts or handle each `Content-Type` explicitly, and test each branch separately. Do not assume query/form/multipart and JSON share the same binder lifecycle.

## 9. Validation, BindingResult, and Exceptions in WebFlux

### 9.1. Conversion errors vs validation errors

~~~text
age=abc
  -> cannot convert String to Integer
  -> binding error; code is typically typeMismatch

age=16
  -> converts cleanly to Integer 16
  -> violates @Min(18), if @Valid/@Validated runs
  -> validation error; code is typically Min

fullName=blocked
  -> String satisfies @NotBlank
  -> custom SignupPolicyValidator reports reserved.name

admin=true
  -> field is not in allowedFields
  -> suppressed field, normally not a FieldError
~~~

These are four distinct outcomes. `BindingResult` provides `getFieldErrors()` and `getSuppressedFields()` to distinguish them. Never return raw `FieldError#getRejectedValue()` in API responses, as it may leak personal data or tokens.

### 9.2. `@Valid` with `BindingResult`

~~~java
@PostMapping("/forms")
public Mono<String> submit(
        @Valid @ModelAttribute("signupForm") SignupForm form,
        BindingResult result) {

    return Mono.just(result.hasErrors() ? "invalid" : "ok");
}
~~~

This is an **illustrative handler**, not part of the runnable project. `BindingResult` must sit **immediately after** the non-reactive `@ModelAttribute` parameter for the handler to inspect errors. Without it, when object-only validation fails, Spring WebFlux typically throws `WebExchangeBindException` mapped to HTTP 400.

When using `@ModelAttribute Mono<SignupForm>`, do not declare a trailing `BindingResult` as with a plain object; handle errors in the reactive chain using `onErrorResume`/`onErrorMap` or an appropriate error handler.

### 9.3. Method validation since Spring 6.1+

A handler with a direct constraint on a parameter such as:

~~~java
@GetMapping("/search")
public Mono<String> search(
        @RequestParam @Min(1) int page) {
    return Mono.just("page:" + page);
}
~~~

can trigger built-in **method validation** (Spring WebFlux 6.1+) and throw `HandlerMethodValidationException` if `page` fails the constraint. This mechanism differs from object-only validation of `@ModelAttribute`, and can cover cascaded `@Valid` constraints when applicable.

`@InitBinder` is where binders/validators are customized for arguments; it **does not automatically turn every `@ModelAttribute` into method validation** and does not replace `@Valid`. If a controller has class-level `@Validated`, method validation may go through an AOP proxy rather than the built-in mechanism; test according to your chosen strategy.

### 9.4. What is the risk when adding a validator?

If you use:

~~~java
binder.setValidator(new SignupPolicyValidator());
~~~

you can accidentally **replace** the global validator; `@NotBlank` and `@Min` backed by the Jakarta provider may stop running as expected. That is why the demo uses:

~~~java
binder.addValidators(new SignupPolicyValidator());
~~~

Multiple validators can contribute errors together. Write tests confirming that both custom rules and Jakarta constraints fire when integrated. When a validator depends on a database or external API, never perform blocking I/O inside the binder's `validate`; reactive service validation after binding is the proper choice.

## 10. Extended Practices: Policies, Converters, and Formatter Scopes

### 10.1. Organizing configuration in multi-controller projects

A maintainable layout:

~~~text
web/
  SignupController.java
  ProfileController.java
  binding/
    CommonBindingAdvice.java
    SignupPolicyValidator.java
    SignupDateFormatter.java
config/
  WebFluxFormattingConfig.java
~~~

You can combine:
- Local `@InitBinder("signupForm")` for rules specific to signup.
- `@ControllerAdvice(basePackageClasses = ...)` for shared binding policies across one area of the application.
- `WebFluxConfigurer#addFormatters` for converters shared across all of WebFlux.
- Separate DTOs per request/use case.
- Spring Security/service layer for authorization; binders only turn input into objects.

Do not dump every policy into a "global" advice and rely on override order across controllers. Whenever changing a policy, test at least one in-scope controller and one out-of-scope controller to confirm it does not leak.

### 10.2. Field-specific formatters

A formatter can be scoped to a field name:

~~~java
@InitBinder("signupForm")
void configure(WebDataBinder binder) {
    binder.addCustomFormatter(
            new DateFormatter("dd/MM/yyyy"), "legacyDate");
}
~~~

This example targets a **`java.util.Date`** field `legacyDate`, not `LocalDate`. It requires importing `org.springframework.format.datetime.DateFormatter`, and the DTO must declare `Date legacyDate`. Do not confuse `DateFormatter` for `java.util.Date` with `java.time.LocalDate` formatters; the runnable code above intentionally uses an editor for `LocalDate`.

For `LocalDate` used across many endpoints, `@DateTimeFormat(pattern = "dd/MM/uuuu")` on the field or a custom `Formatter<LocalDate>` registered in `ConversionService` is cleaner. Avoid ambiguous locale-dependent formats like `01/02/2026` where clients cannot tell day-month from month-day.

### 10.3. Nested/list/map fields

A form with `List<Item> items` or `Map<String, Contact> contacts` can bind from:

~~~text
items[0].code=PEN
items[0].quantity=2
items[1].code=BOOK
contacts[support].email=help@example.com
~~~

With property binding, `allowedFields` should list explicit paths rather than overly broad `items*`:

~~~java
binder.setAllowedFields(
    "items[*].code",
    "items[*].quantity",
    "contacts[support].email"
);
binder.setAutoGrowCollectionLimit(10);
~~~

If collections start empty, auto-grow and nested target instantiation require compatible types/constructors. For a `Map` whose values are objects, initializing expected keys/values on the DTO before binding ensures the binder knows where to bind nested properties. `autoGrowCollectionLimit` does not automatically limit Map key counts, request body size, or permission to modify nested entities.

### 10.4. Input limits

Beyond binder allowlists, configure:
- HTTP body size limits, max in-memory data size, and multipart options in WebFlux/server.
- Maximum number of request fields/list items/map entries.
- Maximum indices, nested property depth, and key/value lengths.
- Data validation constraints (length, min/max, pattern).
- Authorization/ownership checks against the authenticated principal.

`setAutoGrowCollectionLimit(5)` in the demo lowers the risk of allocating arbitrarily huge lists, **but does not guarantee every invalid index becomes a `BindingResult`/HTTP 400**. For public endpoints, test boundary cases and handle exceptions at the appropriate layer.

## 11. Common Mistakes and Diagnosis

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `@InitBinder` does not run | Method not in a scanned controller/advice, or model object name mismatch | Check component scanning, `@ModelAttribute("signupForm")`, and `@InitBinder("signupForm")` |
| Binder runs yet field stays unchanged | `allowedFields` excludes field, missing setter, conversion failed | Inspect `BindingResult#getSuppressedFields()` and `getFieldErrors()` |
| Input with spaces is not trimmed | Advice does not target controller or editor not registered for String | Check `@ControllerAdvice` selector and init method signature |
| `eventDate=25/12/2026` fails to parse | Missing LocalDate editor or formatter registered for wrong type | Register for `LocalDate`/field properly and test format |
| Used `DateFormatter` on a `LocalDate` field | Formatter is for `java.util.Date` | Use `@DateTimeFormat`/`Formatter<LocalDate>`/LocalDate editor |
| `@NotBlank`/`@Min` do not run | Missing `@Valid` or global validator replaced | Add `@Valid`, use `addValidators` instead of replacing |
| `BindingResult` receives no errors | Wrong parameter position or model attribute wrapped in reactive type | Place immediately after non-reactive `@ModelAttribute` |
| JSON still binds `admin` property | `allowedFields` does not govern Jackson `@RequestBody` | Separate JSON DTO, configure deserialization and authorization |
| `setAutoGrowCollectionLimit` does not cap Map | Limit applies only to list/array auto-growth | Enforce Map entry/key limits and request size separately |
| `@ControllerAdvice` applies too broadly | Missing selector or wrong package/type selector | Use `assignableTypes`/`basePackageClasses`/`annotations` |
| Multiple `@InitBinder` methods edit same config | Advice-vs-local override order hard to track | Split responsibilities clearly and avoid overwriting the same property |
| `@InitBinder` tries reactive DB lookup | Synchronous hook; blocking I/O on event loop | Move lookup to reactive service after binding |
| Missing field treated as valid | Missing `@NotNull` or `setRequiredFields` where appropriate | Distinguish field presence from semantic constraints |
| Method-level violation raises different exception | Direct constraints triggered built-in method validation | Handle `HandlerMethodValidationException` alongside `WebExchangeBindException` |
| Tests use `MockMvc` for WebFlux | Confused Servlet MVC with reactive WebFlux | Use `WebTestClient` |
| Spring Boot runs MVC instead of WebFlux | Both servlet web and webflux starters present | Include only WebFlux starter or set app type intentionally |

### Repeatable debug checklist

1. Verify the project actually runs WebFlux with the required dependencies and versions.
2. Start with a small `Content-Type: application/x-www-form-urlencoded` request and exact field names.
3. Ensure `@ModelAttribute("...")` matches `@InitBinder("...")`, and that the controller/advice is scanned.
4. Set a breakpoint/trace in init binder or write an integration test for its effect; never log sensitive data.
5. Distinguish **suppressed** fields from **typeMismatch** errors and validation-**invalid** fields.
6. Check `@Valid` and adjacent `BindingResult`; if using a reactive wrapper, handle errors inside the publisher.
7. Review custom editor/formatter types, formats, and locales; test valid and invalid inputs.
8. If using global advice, verify scope and execution order before local init; avoid conflicting settings.
9. Check whether JSON request bodies go through Jackson, and do not expect form allowlists to apply there.
10. Test boundary indices, field counts, request sizes, and authorization alongside happy paths.

## 12. Practice Exercises

1. Add a `FeedbackController` with `@ModelAttribute("feedbackForm")`. Verify `SignupController`'s `@InitBinder("signupForm")` does not automatically apply to feedback, and that advice using `assignableTypes` targets only the intended controller.
2. Add `@Size(max=80)` to `fullName` and a custom validator rejecting names from a static blocklist. Keep async data lookups in a service.
3. Implement `Formatter<LocalDate>` instead of `PropertyEditorSupport`, then compare parsing/printing of `25/12/2026` and `2026-12-25`.
4. Test `topics[3]`, `topics[10]`, and `topics[100000]`; observe how the property binder behaves and establish your HTTP endpoint's limit policy without assuming all return the same HTTP status.
5. Send JSON containing an `admin` property to another DTO with only valid fields; contrast Jackson's behavior with form `allowedFields`.
6. Try `binder.setDeclarativeBinding(true)` on an immutable record and explain why constructors must be designed as a public input contract.
7. Register a global validator via `WebFluxConfigurer#getValidator()`, then add a local validator via `@InitBinder`. Write tests confirming both contribute errors in the right cases.

## 13. Conclusion

`@InitBinder` in WebFlux is where **binding configuration is registered** for annotated controller arguments—not where HTTP bodies are manually read or business logic runs. Use local `@InitBinder("attributeName")` for form-specific policies, `@ControllerAdvice` to share policies across controller groups, and `WebFluxConfigurer` for genuinely app-wide formatting/validation.

A solid implementation combines:
- Dedicated web request DTOs without sensitive fields.
- `setAllowedFields(...)` to restrict property binding and `setDeclarativeBinding(true)` when a stricter constructor-binding contract is needed.
- Type-accurate formatters/editors tested with both valid and invalid inputs.
- `addValidators(...)` to append Spring validators without accidentally dropping Bean Validation.
- `@Valid`/`@Validated`, `BindingResult`, and exception handlers aligned with the WebFlux lifecycle.
- WebTestClient tests covering binder scope and security, not just happy paths.

## 14. References

- Spring Framework 6.2, **WebFlux DataBinder / @InitBinder**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-initbinder.html
- Spring Framework 6.2, **WebFlux Model Attribute**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2, **WebFlux Data Binding**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/data-binding.html
- Spring Framework 6.2, **WebFlux Controller Advice**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-advice.html
- Spring Framework 6.2, **WebFlux Validation**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html
- Spring Framework 6.2, **WebFlux Configuration – formatters and validators**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html
- Spring Framework 6.2, **DataBinder Javadoc**: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2, **@InitBinder Javadoc**: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/bind/annotation/InitBinder.html
- Spring Boot 3.5, **Testing Spring Boot Applications with WebTestClient**: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
