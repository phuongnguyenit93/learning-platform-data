# @InitBinder: Local Configuration and Shared Configuration via @ControllerAdvice in Spring MVC

## Goals and Scope

In Spring MVC, `@InitBinder` lets you customize **`WebDataBinder`** before Spring binds data from an HTTP request into handler parameters. This lesson explains what `WebDataBinder` does, **local scope inside a controller** versus **shared scope via `@ControllerAdvice`**, model attribute naming, registering converters/formatters, restricting bindable fields, coordinating with validation and `BindingResult`, as well as testing to prevent bugs and mass assignment risks.

Examples use **Java 17+**, **Spring MVC on the Servlet stack**, and **Spring Boot 3.x**. Snippets with file paths form a sample application; isolated snippets are marked as illustrative. Spring WebFlux has a similar data binding mechanism, which is outside the scope here.

## 1. Understanding Data Binding Before Using `@InitBinder`

A form sends a request:

~~~http
POST /appointments HTTP/1.1
Host: localhost:8080
Content-Type: application/x-www-form-urlencoded

visitorName=Lan&date=2026-10-21
~~~

A handler can accept an object:

~~~java
@PostMapping("/appointments")
public String create(@ModelAttribute("appointmentForm") AppointmentForm form) {
    return form.getVisitorName();
}
~~~

This is an illustrative method snippet only: `AppointmentForm` is a JavaBean with `visitorName` and `date` properties.

Simplified Spring MVC flow:

1. Select the handler method matching the request.
2. Create or locate the model attribute to bind, e.g., `appointmentForm`.
3. Create a `WebDataBinder` bound to the corresponding target and object name.
4. Apply eligible `@InitBinder` methods, including shared ones from `@ControllerAdvice` and those declared in the controller.
5. Bind request data into the object via constructor binding and/or property binding as appropriate, while converting types (e.g., string `2026-10-21` into `LocalDate`).
6. If the handler requests validation (`@Valid`, `@Validated`), Spring runs validation; the handler can read errors via a properly placed `BindingResult`.
7. Invoke the handler with the bound arguments.

Each binding operation gets a **dedicated `WebDataBinder`**, so editor/formatter settings or field lists configured on the binder apply to that binding pass. An `@InitBinder` method is **not an HTTP endpoint**, does not directly produce responses, does not replace `@PostMapping`, and typically returns `void`.

`@InitBinder` is declared in a `@Controller`/`@RestController` or `@ControllerAdvice` class. The most common parameter is `WebDataBinder`. Depending on version and configuration, supported context parameters such as `WebRequest` or `Locale` can also be used; do not declare an arbitrary `@ModelAttribute` as a parameter to the `@InitBinder` method itself.

## 2. Local Scope: Placing `@InitBinder` Inside One Controller

~~~java
@RestController
class AppointmentController {

    @InitBinder
    void configureAllBindersInThisController(WebDataBinder binder) {
        binder.setAllowedFields("visitorName", "date");
    }

    // @RequestMapping/@PostMapping handlers go here...
}
~~~

The snippet above only illustrates structure and is not a standalone runnable Java file (missing imports and handlers). An unnamed `@InitBinder` can apply to all eligible binders within that controller. If a controller handles several different forms, applying one shared field list to all of them can unintentionally block valid cases.

To restrict to a specific model attribute **`object name`**, use `@InitBinder("appointmentForm")`:

~~~java
@InitBinder("appointmentForm")
void configureAppointment(WebDataBinder binder) {
    binder.setAllowedFields("visitorName", "date");
}
~~~

Matching handler declaration:

~~~java
@PostMapping("/appointments")
public String create(
        @ModelAttribute("appointmentForm") AppointmentForm form) {
    return form.getVisitorName();
}
~~~

The name `appointmentForm` must match. The `value` parameter of `@InitBinder` also accepts multiple names, such as `@InitBinder({"appointmentForm", "bookingForm"})`. This name refers to the **model attribute or request parameter handled by the binder**, not a URL, a Java class name, or a method name.

When the same controller has `@InitBinder("appointmentForm")` and `@InitBinder("profileForm")`, each binder can receive a different configuration. Do not pick names by habit without checking: if the model attribute has a different name, the local configuration will not run for the intended object.

## 3. Shared Scope: `@InitBinder` in `@ControllerAdvice`

~~~java
@ControllerAdvice
public class SharedBindingAdvice {

    @InitBinder
    public void configure(WebDataBinder binder) {
        binder.registerCustomEditor(
                String.class, new StringTrimmerEditor(true));
    }
}
~~~

This is an illustrative snippet requiring imports for `WebDataBinder`, `StringTrimmerEditor`, and `@ControllerAdvice`/`@InitBinder`. The editor is created during binder initialization and trims leading/trailing whitespace on bound `String` properties; the `true` argument converts empty strings after trimming into `null`.

Without selectors, `@ControllerAdvice` has broad scope and can apply across controllers managed by Spring MVC. You can narrow the advice with:

~~~java
@ControllerAdvice(assignableTypes = {
        AppointmentController.class, ProfileController.class
})
~~~

Or use package/annotation selectors, such as `basePackages = "com.example.demo.form"` or `annotations = RestController.class`. Selectors here **choose which controllers** are targeted, whereas `@InitBinder("appointmentForm")` **chooses which binder targets** inside the selected controllers are affected. These two scoping layers complement each other.

In large applications, avoid blindly deploying a configuration that alters every string or field across all controllers. For instance, trimming `String` values may make sense for display names but can corrupt passwords, signatures, tokens, or strings where whitespace is significant. Scope each advice deliberately.

**Quick comparison:**

| Declaration | Scope |
| --- | --- |
| `@InitBinder` in `AppointmentController` | Eligible binders within that controller |
| `@InitBinder("appointmentForm")` in `AppointmentController` | Binders with object name `appointmentForm` in that controller |
| `@InitBinder` in `@ControllerAdvice` without selectors | Eligible binders across controllers within advice scope |
| `@InitBinder("appointmentForm")` in advice with selectors | Controllers matching selector **and** binders matching attribute name |
| `WebMvcConfigurer#addFormatters(...)` | Registers converters/formatters in shared MVC configuration |

If multiple advices can apply, configuration must avoid conflicts (such as two places registering editors for the same type). Do not rely on implicit ordering of overlapping configurations; separate scopes clearly and test the final behavior.

## 4. What Can You Configure on `WebDataBinder`?

| Mechanism | Meaning | When to use |
| --- | --- | --- |
| `setAllowedFields(...)` | Restricts **property binding** to declared fields only | Preventing clients from sending unexpected properties |
| `setRequiredFields(...)` | Requires fields to be present during input binding | Specific request-field presence rules, not a replacement for validation |
| `registerCustomEditor(...)` | Registers a `PropertyEditor` for conversion | Legacy editor needs or binder-specific logic |
| `addCustomFormatter(...)` | Registers a `Formatter` for a type/field | Converting values with parse and display rules |
| `addValidators(...)` | Adds an `org.springframework.validation.Validator` | Extra business checks alongside Bean Validation |
| `setDeclarativeBinding(true)` | Enforces explicit binding declaration (when supported by version) | Restricting property binding on objects needing protection |

`setAllowedFields` is an **allowlist for setter/property binding**, especially worth considering when binding objects that have both user-editable and internal properties. `setRequiredFields` checks at the binding layer whether a field was supplied, which **differs** from `@NotBlank`, `@NotNull`, and `@Size` checking value validity. In modern APIs, dedicated input DTOs and Bean Validation are usually preferred.

A common way to convert dates is directly using:

~~~java
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
private LocalDate date;
~~~

When custom rules apply across multiple controllers, consider registering a `Converter` or `Formatter` via `WebMvcConfigurer#addFormatters` and `FormattingConversionService`. Use `@InitBinder` for per-binder customization only when narrow scope is intentional.

**Security:** per Spring MVC documentation, `allowedFields` is a list for property binding and should not be assumed to control constructor binding in all cases. For objects constructed from request parameters, use dedicated DTOs, control constructor inputs, and configure declarative binding appropriately. Never bind directly into an entity/domain object with many sensitive properties and hope the frontend "won't send" them.

## 5. Runnable Application: One Local Config and One Shared Advice

Create a Maven project from Spring Initializr with **Java 17+**, **Spring Boot 3.x**, and dependencies **Spring Web**, **Validation**, and **Spring Boot Starter Test**. The corresponding artifacts are `spring-boot-starter-web`, `spring-boot-starter-validation`, and `spring-boot-starter-test`. Keep the Java package as `com.example.demo`.

Structure:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/AppointmentController.java
src/main/java/com/example/demo/ProfileController.java
src/main/java/com/example/demo/FormBindingAdvice.java
src/test/java/com/example/demo/BindingControllerTest.java
~~~

### 5.1. Entry Point

**`src/main/java/com/example/demo/DemoApplication.java`**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 5.2. Shared `@ControllerAdvice` Configuration for Two Controllers

**`src/main/java/com/example/demo/FormBindingAdvice.java`**

~~~java
package com.example.demo;

import org.springframework.beans.propertyeditors.StringTrimmerEditor;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.InitBinder;

@ControllerAdvice(assignableTypes = {
        AppointmentController.class, ProfileController.class
})
public class FormBindingAdvice {

    @InitBinder
    public void trimStrings(WebDataBinder binder) {
        binder.registerCustomEditor(
                String.class, new StringTrimmerEditor(true));
    }
}
~~~

This advice applies only to the two listed controllers. When binding form objects in either controller, `StringTrimmerEditor` normalizes whitespace. Because this demonstrates a whitespace-trimming rule, **do not** extend the advice to forms containing secrets/passwords if the application must preserve every character verbatim.

### 5.3. `@InitBinder("appointmentForm")` Restricting Local Fields

**`src/main/java/com/example/demo/AppointmentController.java`**

~~~java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;
import java.util.Map;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AppointmentController {

    @InitBinder("appointmentForm")
    public void restrictFields(WebDataBinder binder) {
        binder.setAllowedFields("visitorName", "date");
    }

    @PostMapping(
            path = "/appointments",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> create(
            @Valid @ModelAttribute("appointmentForm") AppointmentForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "invalid appointment"));
        }

        return ResponseEntity.ok(new AppointmentResponse(
                form.getVisitorName(),
                form.getDate(),
                form.getRole()));
    }

    public record AppointmentResponse(
            String visitorName,
            LocalDate date,
            String role) {
    }

    public static class AppointmentForm {
        @NotBlank
        private String visitorName;

        @NotNull
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        private LocalDate date;

        // Property intentionally included to demonstrate not binding from request.
        private String role = "viewer";

        public AppointmentForm() {
        }

        public String getVisitorName() {
            return visitorName;
        }

        public void setVisitorName(String visitorName) {
            this.visitorName = visitorName;
        }

        public LocalDate getDate() {
            return date;
        }

        public void setDate(LocalDate date) {
            this.date = date;
        }

        public String getRole() {
            return role;
        }

        public void setRole(String role) {
            this.role = role;
        }
    }
}
~~~

**Detailed breakdown of the example:**

- `@ModelAttribute("appointmentForm")` matches the name in `@InitBinder("appointmentForm")`; thus the `visitorName`, `date` allowlist applies to the form.
- `AppointmentForm` has a no-args constructor and setters, so this example specifically demonstrates **property binding**. Even if the client sends `role=admin`, the `role` property is not in the allowlist and keeps `"viewer"`.
- `@DateTimeFormat(iso = ISO.DATE)` instructs Spring to convert strings like `yyyy-MM-dd` to `LocalDate`; an invalid format creates a binding error.
- `@Valid` runs Bean Validation after binding. `@NotBlank` rejects an empty `visitorName`, and `@NotNull` rejects a null `date`.
- `BindingResult errors` must be placed **immediately after the corresponding model attribute parameter**. If placed in the wrong position, Spring MVC does not pass that attribute's errors to the handler in the same way.
- If errors exist, the endpoint explicitly returns HTTP 400. Otherwise, it returns JSON including `role` to **make the allowlist effect visible**; real production endpoints should not expose internal info just to demonstrate this behavior.

`@InitBinder` is not the place to authenticate identities or enforce access permissions: the `role` check in this example illustrates **mass assignment** prevention, while real authorization must be handled by the security/business layer.

### 5.4. Second Controller Inheriting the Same Advice Rule

**`src/main/java/com/example/demo/ProfileController.java`**

~~~java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @PostMapping(
            path = "/profiles",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> create(
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "invalid profile"));
        }

        return ResponseEntity.ok(
                Map.of("displayName", form.getDisplayName()));
    }

    public static class ProfileForm {
        @NotBlank
        private String displayName;

        public ProfileForm() {
        }

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }
    }
}
~~~

`ProfileController` declares no `@InitBinder` of its own, yet it **is still selected by the advice** via `assignableTypes`; therefore `displayName` input is also trimmed. Meanwhile, the allowlist in `AppointmentController` does **not** affect `profileForm`: the two controllers have separate local restrictions.

## 6. Running Requests and Explaining Results

After creating the files matching the structure above, run:

~~~bash
./mvnw spring-boot:run
~~~

On Windows with Maven Wrapper: `mvnw.cmd spring-boot:run`. Without a wrapper, use `mvn spring-boot:run` if Maven is installed.

Try calling with `curl`:

~~~bash
curl -i -X POST "http://localhost:8080/appointments"   -d "visitorName=%20%20Lan%20%20"   -d "date=2026-10-21"   -d "role=admin"
~~~

This uses shell syntax; in PowerShell, use `curl.exe` with all arguments on a single line. `curl -d` sends an `application/x-www-form-urlencoded` body by default, matching the controller's `consumes`.

Result **200 OK** (JSON property order does not matter):

~~~json
{"visitorName":"Lan","date":"2026-10-21","role":"viewer"}
~~~

Why:

- The shared advice scoped to `AppointmentController` trimmed `"  Lan  "` to `"Lan"`.
- The local binder for `appointmentForm` permitted `visitorName` and `date`, while excluding `role` from property binding, so `viewer` was not replaced by `admin`.
- `@DateTimeFormat` bound the valid date; `@Valid` confirmed data validity.

Try the second controller:

~~~bash
curl -i -X POST "http://localhost:8080/profiles"   -d "displayName=%20%20Mai%20%20"
~~~

HTTP **200 OK**, expected body:

~~~json
{"displayName":"Mai"}
~~~

Try sending a whitespace-only name or an invalid date format:

~~~bash
curl -i -X POST "http://localhost:8080/appointments"   -d "visitorName=%20%20%20"   -d "date=2026-10-21"

curl -i -X POST "http://localhost:8080/appointments"   -d "visitorName=Lan"   -d "date=21/10/2026"
~~~

Both requests receive **400 Bad Request** in the example: the first request leaves `visitorName` as `null` after trimming, failing `@NotBlank`; the second fails to parse `date` as ISO. The illustrative controller returns:

~~~json
{"error":"invalid appointment"}
~~~

These examples assume the application runs on Spring Boot's default port `8080` without Spring Security requiring authentication/CSRF. If Spring Security is added to the project, configure authentication and CSRF appropriately before running the `curl` commands above.

## 7. Testing with MockMvc to Prove Binder Scope

Add **`src/test/java/com/example/demo/BindingControllerTest.java`**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = {
        AppointmentController.class, ProfileController.class
})
@Import(FormBindingAdvice.class)
class BindingControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void localAllowlistAndSharedTrimmingWorkTogether() throws Exception {
        mockMvc.perform(post("/appointments")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("visitorName", "  Lan  ")
                        .param("date", "2026-10-21")
                        .param("role", "admin"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.visitorName").value("Lan"))
                .andExpect(jsonPath("$.date").value("2026-10-21"))
                .andExpect(jsonPath("$.role").value("viewer"));
    }

    @Test
    void sharedAdviceAlsoAppliesToProfileController() throws Exception {
        mockMvc.perform(post("/profiles")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "  Mai  "))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value("Mai"));
    }

    @Test
    void blankVisitorNameFailsValidation() throws Exception {
        mockMvc.perform(post("/appointments")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("visitorName", "   ")
                        .param("date", "2026-10-21"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void invalidDateFailsConversion() throws Exception {
        mockMvc.perform(post("/appointments")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("visitorName", "Lan")
                        .param("date", "21/10/2026"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Run:

~~~bash
./mvnw test
~~~

The first test simultaneously proves **local scope** (`role` is ignored) and **shared scope** (the name is trimmed). The second proves the advice applies to the other controller. The final two tests catch type conversion vs. validation errors. `@Import(FormBindingAdvice.class)` ensures the advice is present in the Spring MVC test slice, even if test component scanning differs from the main application.

`MockMvc` simulates requests to Spring MVC without opening a real HTTP port; it tests binders, argument resolution, validation, and controller responses. When a custom `SecurityFilterChain` exists, tests must configure appropriate security.

## 8. Registering `PropertyEditor`, `Formatter`, and `Validator`: Where Should They Go?

### `PropertyEditor`: The Classic Approach

~~~java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.registerCustomEditor(
            String.class, new StringTrimmerEditor(true));
}
~~~

This snippet is used in the main example. `PropertyEditor` instances are often stateful, so **do not share a single mutable instance across multiple requests/threads**. Instantiate a fresh one during binder initialization as shown above. For `java.util.Date`, Spring also has `CustomDateEditor`, though with modern `java.time`, `@DateTimeFormat`/`Formatter` are usually cleaner.

### `Formatter`: When Consistent Parse/Print Is Needed for a Type

The illustrative snippet below is for `java.util.Date` properties, not `LocalDate`:

~~~java
@InitBinder("legacyForm")
void initLegacyDate(WebDataBinder binder) {
    binder.addCustomFormatter(new DateFormatter("yyyy-MM-dd"));
}
~~~

In a controller context, you need to import `org.springframework.format.datetime.DateFormatter` and `org.springframework.web.bind.WebDataBinder`. If a formatter applies across many places with the same rule, consider placing it in the shared MVC `ConversionService` instead of repeating `@InitBinder`.

### `Validator`: Adding Business Rules

You can use `binder.addValidators(customValidator)` to register a validator implementing `org.springframework.validation.Validator`. Such a validator must implement `supports(Class<?>)` and `validate(Object, Errors)`. At runtime, Spring verifies whether the target type matches the validator; registering an incompatible validator can cause configuration errors.

`@InitBinder` only **registers** the validator; it does not mean every handler automatically validates without appropriate validation triggers. Use `@Valid` or `@Validated` on the model attribute when you want Spring to run validation, or invoke checks explicitly if your design calls for it. With standard Bean Validation, use `@NotBlank`, `@Size`, `@Email`, `@NotNull`, and inspect `BindingResult`.

If replacing an existing validator, understand the difference between `addValidators` (append) and `setValidator` (set/replace). Do not inadvertently overwrite the default Bean Validation validator.

## 9. Important Limitation: `@InitBinder` Does Not Replace JSON Deserialization

`@ModelAttribute` typically accepts query/form data from requests and binds via `WebDataBinder`, whereas `@RequestBody` typically reads JSON via `HttpMessageConverter`/Jackson. Example:

~~~java
@PostMapping("/users")
public void create(@RequestBody CreateUserRequest request) {
    // Jackson reads the request's JSON into CreateUserRequest.
}
~~~

This is an incomplete illustrative snippet. A `StringTrimmerEditor` attached to `WebDataBinder` **does not mean** strings Jackson reads from JSON are automatically trimmed. For `@RequestBody`, use an appropriate mechanism at the Jackson/deserializer layer, a dedicated data normalizer, or handle it in the service/DTO. `WebDataBinder` machinery may still be involved in **validation** of the object produced by `@RequestBody`, but do not confuse that with form setter binding.

Likewise, `@InitBinder` is not a substitute for `@ControllerAdvice @ExceptionHandler`: the two callback types have distinct roles. `@InitBinder` **configures binding**; `@ExceptionHandler` **handles exceptions**. A single advice class can contain both, while keeping responsibilities clearly separated.

## 10. Binding Security: Allowlists, Constructor Binding, and Mass Assignment

Suppose a `User` entity has properties `displayName`, `email`, and `isAdmin`. If a request binds directly onto the entity via setters, an attacker can add `isAdmin=true` even when the UI never displays that field. That is **mass assignment**.

Preferred safeguards:

1. Create an **input DTO** containing only fields the user is authorized to supply; map the DTO to the entity in the service layer according to business rules.
2. When property binding is needed, use `WebDataBinder#setAllowedFields("fieldA", "fieldB")` per model attribute. This primarily protects **setter/property binding** and should not be equated with controlling constructor parameters.
3. On Spring Framework versions supporting `setDeclarativeBinding(true)`, consider declarative binding mode: constructor binding continues to work while property binding requires a configured allowlist. Know what inputs your DTO constructor accepts and test explicitly.
4. Enforce authorization in the service/security layer based on the authenticated user and server-side state, never trusting `role`, `isAdmin`, or `ownerId` sent by the client.
5. Do not use `setDisallowedFields` as a default defense when an allowlist works: denylists easily miss newly added properties. Newer Spring versions also steer away from this API.

In the sample code, the `role` field with a setter exists purely to demonstrate the allowlist's effect; real API designs should omit such a field from form DTOs if it is not valid client input.

## 11. Common Mistakes and How to Verify

| Symptom | Likely cause | How to verify |
| --- | --- | --- |
| Local `@InitBinder` does not run | Wrong `@ModelAttribute` name or binder not in expected controller | Compare `@InitBinder("...")` and `@ModelAttribute("...")` |
| Advice has no effect | Controller does not match `assignableTypes`, `basePackages`, or `annotations` | Check selector and Spring component-scan locations |
| Editor runs for unintended forms | Advice is too broad or unnamed binder lacks restrictions | Narrow selector, split rules by controller/attribute |
| Date conversion fails | String format mismatches formatter/`@DateTimeFormat` | Inspect input and expected pattern |
| `BindingResult` misses expected errors | Misplaced parameter or handler lacks matching attribute | Place immediately after `@Valid @ModelAttribute` parameter |
| Internal field unexpectedly changed | Binding directly to overly broad object; missing allowlist | Use DTOs, `setAllowedFields`, test sending unexpected fields |
| Valid field fails to bind | Allowlist is missing the property name | Add the exact property after verifying the input contract |
| Trimming has no effect on JSON `@RequestBody` | Jackson handles JSON separately | Configure Jackson or use a dedicated normalizer |
| Custom editor fails randomly under load | Sharing stateful mutable editor across threads | Create a new editor per binder; prefer stateless formatter/converter |
| Handler still returns 400 without calling service | Binding/validation failure occurred earlier | Inspect logs, `BindingResult`, or configured exception handlers |

When verifying fields rejected by an allowlist, `BindingResult#getSuppressedFields()` reports which request field names were suppressed. This is a useful diagnostic signal; it does not replace verifying that the API never persists unauthorized values.

## 12. Review Questions

**1. Why is `@InitBinder("appointmentForm")` not equivalent to `@InitBinder`?**

Because the named variant applies only to binders whose attribute/request parameter name matches; the unnamed variant has broader scope across the owning controller or advice.

**2. If three controllers share a form normalization rule, where should it live?**

Prefer a `@ControllerAdvice` with selectors matching those exact three controllers, or a shared MVC converter/formatter configuration if it is an application-wide conversion rule.

**3. When sending `role=admin` to the sample form, why is `role=viewer` still returned?**

Because `AppointmentForm` uses property binding and the allowlist contains only `visitorName` and `date`; the client-supplied `role` value is ignored. Real access permissions must still be enforced on the server.

**4. Can `@Valid` replace an allowlist?**

No. Validation checks values after/alongside binding; an allowlist restricts which properties may be bound. They answer different questions and may both be needed.

**5. Why doesn't a String editor on WebDataBinder automatically trim JSON `@RequestBody`?**

Because JSON is deserialized by `HttpMessageConverter` (usually Jackson), which is a different pipeline from form/query property binding through `WebDataBinder`.

## 13. Pre-Project Checklist

- Name model attributes explicitly when a binder targets a single form type; verify names in `@InitBinder` and `@ModelAttribute` match.
- Place truly shared rules in an appropriately scoped advice; use global `ConversionService` when the need is purely shared converters/formatters.
- Use input DTOs, allowlists for setter binding where needed, and validation with `@Valid`/`BindingResult`; authenticate and authorize on the server.
- Distinguish conversion errors, validation errors, and suppressed fields. Test valid, missing, malformed, and unauthorized-field cases.
- Do not use `@InitBinder` as a substitute for JSON deserializers, exception handlers, or security filters.

## Official References

- [Spring Framework — `@InitBinder` in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring Framework — `@ModelAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Controller Advice](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html)
