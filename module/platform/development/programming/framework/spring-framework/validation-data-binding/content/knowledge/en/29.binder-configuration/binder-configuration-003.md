# @ControllerAdvice and Shared Binder Configuration in Spring MVC

## 1. The Problem: Multiple Controllers Need a Common Data-Binding Policy

In Spring MVC, whenever the framework turns HTTP request parameters into a **model attribute**, `WebDataBinder` can participate in object instantiation, type conversion, recording binding errors, and invoking validators. An application with multiple controllers commonly encounters shared requirements:

- Restricting how requests are allowed to write data into objects.
- Applying a safe policy for **property binding** to reduce mass-assignment risk.
- Registering formatters, converters, or validators according to a shared convention.
- Allowing individual controllers to declare controlled exceptions for specific forms.
- Avoiding copying the same `@InitBinder` method into dozens of controllers.

Spring supports declaring `@InitBinder` methods inside **`@ControllerAdvice`** to establish a binder policy across multiple controllers. This feature is for **initializing/configuring binders**, distinct from `@ExceptionHandler` (which handles exceptions) and method-level `@ModelAttribute` (which can prepare model data).

Guiding example:

```java
@ControllerAdvice
public class SharedBindingPolicy {

    @InitBinder
    void initialize(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
```

The idea: enable **constructor binding** by default, while **property binding** does not run unless `allowedFields` is configured. A controller handling a mutable form can add:

```java
@InitBinder("profile")
void profileBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "city");
}
```

The two snippets above are only illustrative excerpts; the hands-on section below provides full source code, Gradle build, Spring Boot setup, and `MockMvc` tests.

**Reference versions:** Java 17+, Spring Boot 3.3.x, Spring Framework 6.1–6.2, Servlet Spring MVC. `setDeclarativeBinding(true)` was added in Spring Framework 6.1, so do not copy this code verbatim into Spring Framework 5.x. Security recommendations are general principles; specific APIs must be verified against your version.

## 2. Components and Responsibility Boundaries

### 2.1. What Is `WebDataBinder`?

`org.springframework.web.bind.WebDataBinder` is the binder for web environments. It inherits capabilities from `DataBinder` to:

- Bind request parameters/web values onto a model object.
- Convert strings into Java types such as `Integer`, `LocalDate`, enums, or custom types via `ConversionService`, `PropertyEditor`, and `Formatter`.
- Select or restrict writable properties.
- Record type-mismatch errors into `BindingResult`.
- Trigger configured validators when Spring requests validation.

An object being bound does not guarantee it is validated: `@Valid`/`@Validated` at the boundary and appropriate validators remain separate concerns. Nor does it imply the data is authorized or domain-valid.

### 2.2. `@InitBinder` Is a Configuration Hook

`@InitBinder` marks a **binder initializer method**, typically taking a `WebDataBinder` parameter and returning `void`. The annotation can be placed:

- Inside `@Controller` or `@RestController`: affects that controller **locally**.
- Inside `@ControllerAdvice`: can affect multiple controllers within the selected scope.
- Inside `@RestControllerAdvice`: also supports `@InitBinder` because this annotation combines `@ControllerAdvice` with `@ResponseBody`; the `@ResponseBody` part primarily affects exception-handler return bodies.

Local controller example:

```java
@RestController
class ChangeEmailController {

    @InitBinder("changeEmail")
    void configure(WebDataBinder binder) {
        binder.setAllowedFields("newEmail");
    }
}
```

This is an illustrative class without an endpoint yet. The name `"changeEmail"` is the **model attribute name**, not a request mapping name, not a Java class name, and not a validation group.

### 2.3. `@ControllerAdvice` Is the Sharing Mechanism

`@ControllerAdvice` is a stereotype component detected by Spring via component scanning or bean declarations. It can contain:

| Annotation in Advice | Role |
| --- | --- |
| `@InitBinder` | Configures binders for controllers within the advice's scope |
| `@ModelAttribute` on a method | Prepares shared model attributes |
| `@ExceptionHandler` | Handles handler/controller exceptions within the advice's scope |

Placing `@ControllerAdvice` on a class **does not automatically turn it into a validator**. Methods inside still must be annotated and declared for their intended purpose. An advice class containing only `@InitBinder` does not need an `@ExceptionHandler`.

### 2.4. Distinguishing Three Commonly Confused "Global" Mechanisms

| Configuration Location | Scope / Timing | When to Use |
| --- | --- | --- |
| `@InitBinder` in a controller | Binders of that controller or named attribute | Forms/endpoints needing custom rules |
| `@InitBinder` in `@ControllerAdvice` | Binders of controllers matched by the advice | Shared binder policy across a group of controllers |
| `WebMvcConfigurer#addFormatters` | Shared MVC `FormattingConversionService` | Converters/formatters genuinely used application-wide |
| `WebBindingInitializer`/`ConfigurableWebBindingInitializer` | Binder initialization at the MVC infrastructure layer | Lower-level extension points and deep framework customization |
| `@ExceptionHandler` / `ResponseEntityExceptionHandler` | After an exception is thrown | Standardizing error responses; does not restrict bound fields |
| `Validator` / Jakarta Validation provider | When executing constraints | Validating field values; does not replace writable-property policies |

Pick the tool matching the boundary: **conversion**, **binding policy**, **validation**, and **exception response** are linked steps, not the same operation.

## 3. Lifecycle: Global `@InitBinder` Before Local `@InitBinder`

For Spring MVC annotated controllers, the mechanism can be pictured as:

```text
HTTP request
      |
      v
DispatcherServlet selects handler
      |
      v
Argument resolver needs to bind model attribute
      |
      v
Create WebDataBinder for object/attribute
      |
      +--> @InitBinder from matching @ControllerAdvice
      |      - declarative binding
      |      - shared formatters/validators
      |
      +--> Local @InitBinder in controller
      |      - per-attribute-name customization
      |      - allowedFields for mutable forms
      |
      v
Constructor binding / property binding (per policy)
      |
      v
Type conversion -> BindingResult (if errors occur)
      |
      v
@Valid/@Validated when requested
      |
      v
Controller receives object and BindingResult
```

**Important ordering:** According to the Spring MVC documentation, `@InitBinder` methods in `@ControllerAdvice` are applied **before** local `@InitBinder` methods in the controller. Conversely, `@ExceptionHandler` resolution checks local before global. Do not extrapolate ordering from one advice method type to another.

This lets you establish a baseline policy first, and then allow a controller to **add** local customization. However, if both global and local methods call setters configuring the **same binder property**, the later configuration may replace the earlier one per setter semantics. Do not treat advice as an immutable security firewall that a local controller cannot override.

Reasonable example:

```java
// Global:
binder.setDeclarativeBinding(true);

// Local:
binder.setAllowedFields("displayName", "city");
```

Desired outcome: controllers do not open property binding indiscriminately; the controller handling `profile` permits property binding for **only the two declared fields**. Conversely, a local binder calling `setDeclarativeBinding(false)` can disable the shared policy—that must be a strictly reviewed and tested decision.

### 3.1. Configuration Does Not "Bind the Request" When `@InitBinder` Runs

`@InitBinder`'s job is to **configure** how the binder behaves, not to invoke business services or assign the entire request itself. The binder is used by the argument resolver in the next step. Nor should you assume every HTTP request always creates the same number of binders: the number of binders and target objects depends on handler signatures, attributes, and the framework's validation path.

### 3.2. What Scope Does `@InitBinder("name")` Restrict?

`@InitBinder("profile")` specifies the attribute name that the customizer applies to. If the controller declares:

```java
@ModelAttribute("profile") ProfileForm form
```

then the two names match. If you rename it to `@ModelAttribute("userProfile")` and forget to update `@InitBinder`, the allowlist may no longer be registered for the new attribute.

Use explicit names on both annotations whenever a specific security policy is involved. Do not rely on convention-inferred names, especially when renaming DTO types or refactoring parameters.

## 4. When Should You Use a Global `@ControllerAdvice`?

### 4.1. Default Applies to All Controllers

```java
@ControllerAdvice
public class GlobalBinderAdvice {
    @InitBinder
    void customize(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
```

When Spring scans this class, the advice can affect `@Controller` and `@RestController` beans across the MVC application without direct references from individual controllers.

Benefits:

- A uniform default input policy is enforced.
- Less duplicated code.
- New controllers inherit the baseline policy, reducing accidental omissions.
- Property binding can be guarded by requiring a local allowlist.

Downside: introducing a "global" configuration can change the behavior of existing forms. Mutable forms relying on setter binding without an allowlist may stop binding as before once `declarativeBinding` is enabled.

### 4.2. Applying Only to a Subset of Controllers

`@ControllerAdvice` supports selectors:

```java
@ControllerAdvice(basePackages = "com.example.app.web.forms")
public class FormsOnlyAdvice { /* ... */ }
```

```java
@ControllerAdvice(basePackageClasses = FormController.class)
public class PackageAdvice { /* ... */ }
```

```java
@ControllerAdvice(assignableTypes = FormController.class)
public class OneControllerAdvice { /* ... */ }
```

```java
@ControllerAdvice(annotations = RestController.class)
public class RestControllersAdvice { /* ... */ }
```

These are **four independent illustrative options**, not four classes to add simultaneously to the hands-on project. `basePackageClasses` is safer during refactoring than hard-coded package names, but it selects the **package containing the given type**, not just that single type. `assignableTypes` targets a specific controller class or parent class/interface.

**Common pitfall:** If you combine multiple selector types on the same `@ControllerAdvice`, Spring applies **OR** logic: matching **any** selector is enough. Therefore:

```java
@ControllerAdvice(
    basePackages = "com.example.app.web.forms",
    annotations = RestController.class
)
```

does not mean "only `@RestController` in the `forms` package"; it can select controllers in that package **or** `@RestController` beans in other packages. If you need complex AND logic, do not assume it from selectors; separate policies appropriately or use a clear marker annotation/controller hierarchy.

Selectors are evaluated at runtime. Avoid adding overly complex selectors unless needed; they make maintenance and predicting scope harder.

### 4.3. Can `@RestControllerAdvice` Configure Binders?

Yes:

```java
@RestControllerAdvice
public class RestBindingAdvice {

    @InitBinder
    void init(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
```

`@RestControllerAdvice` does not restrict scope to `@RestController` solely by its name; by default it has the same broad scope as `@ControllerAdvice`. The "Rest" part primarily indicates that exception-handler methods follow `@ResponseBody` semantics. If you want to target only `@RestController`, specify `annotations = RestController.class` explicitly.

## 5. Property-Binding Security: `allowedFields` Is Central

### 5.1. Mass Assignment / Over-Posting

Suppose a web application accepts an object with setters:

```java
public class Account {
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

If Spring property binding can populate every writable property, a malicious client can send:

```text
displayName=Lan&admin=true
```

Even if the UI renders only the `displayName` input, the actual HTTP request can include `admin`. That is **mass assignment**. `@Valid` alone does not protect against this: it checks constraints, not which properties the client is permitted to control.

Preferred defenses:

1. Endpoint-specific DTOs containing only fields the client is allowed to submit.
2. Constructor binding with an explicit parameter list, well-suited to immutable records.
3. When mutable JavaBean/property binding is needed, `setAllowedFields` with a specific, narrow list.
4. Business authorization and DTO → domain mapping in the service layer before persisting data.
5. Regression tests that intentionally submit extra sensitive fields.

### 5.2. `setAllowedFields` and `setDisallowedFields`

Allow exactly two fields:

```java
binder.setAllowedFields("displayName", "city");
```

Block via denylist:

```java
binder.setDisallowedFields("admin", "role");
```

Spring recommends an **allowlist** because it is explicit and less prone to omissions as schemas evolve. `allowedFields` patterns match **case-sensitively**, whereas `disallowedFields` matching is **case-insensitive**. When using wildcards, understand the exact property paths being opened.

For example, `"address.*"` may expose more nested fields than intended. Use `"address.city"` and `"address.postalCode"` if only those two fields are needed. Avoid `"*"` on DTOs with sensitive setters.

**Do not treat a denylist as a safe fallback** without schema-review policies; even a single newly added setter like `setCanApprove` can open an unintended assignment path.

### 5.3. `getSuppressedFields` Reveals Blocked Inputs

`BindingResult#getSuppressedFields()` returns field names excluded from property binding due to restriction policies. For example:

```java
String[] suppressed = bindingResult.getSuppressedFields();
```

If a request tries sending `admin=true` while `allowedFields` contains only `displayName` and `city`, `admin` can appear in `suppressed`. That **does not by default create a Bean Validation violation**; an ignored field may leave `hasErrors()` returning `false`.

If the system must reject the entire request upon over-posting, add dedicated handling for `suppressedFields`, such as returning HTTP 400 or logging a security event per policy. Do not assume `@NotBlank` will catch and reject a suppressed field.

### 5.4. Constructor Binding and `allowedFields` Are Not Equivalent

A record:

```java
public record AccountInput(
        String displayName,
        boolean admin
) {}
```

can still be instantiated via its constructor with `admin=true` from the request if model-attribute constructor binding accepts that parameter. `setAllowedFields("displayName")` applies to **property binding**; it does not "remove" the `admin` parameter from a declared constructor.

Therefore, first **design input DTOs properly**: exclude roles, approval flags, or internal `ownerId` fields from the constructor of objects clients populate. `setDeclarativeBinding` is an extra guardrail, not a way to sanitize a DTO that already exposes sensitive fields.

## 6. `setDeclarativeBinding(true)`: A Safe Baseline Policy

As of Spring MVC 6.1+, `WebDataBinder` can be configured with:

```java
binder.setDeclarativeBinding(true);
```

Effect:

- Constructor binding remains available.
- Property binding runs **only** if `allowedFields` is configured.
- Controllers accepting immutable DTOs are protected from unintended writable-property assignment.
- Older mutable forms without `allowedFields` may no longer populate as before.

In a large application, a useful structure is:

```text
@ControllerAdvice
    |
    +--> global @InitBinder
           binder.setDeclarativeBinding(true)
                     |
                     v
          Constructor DTO (record) ------> Bind constructor arguments
                     |
                     +--> Mutable form
                              |
                              +--> Local @InitBinder("profile")
                                     setAllowedFields("displayName", "city")
                              |
                              v
                         Bind two setter properties only
```

This is a **default-deny model for property binding**, not a complete security policy for every input format. For `@RequestBody` JSON, Jackson performs deserialization via `HttpMessageConverter`, so `WebDataBinder`'s `setAllowedFields` **does not block JSON properties** that Jackson reads. See section 11 to avoid this critical misconception.

## 7. Complete Project: Shared Policy and Local Exception

We build a Spring Boot 3.3.x application:

- `POST /forms/register` receives an **immutable record** via `@ModelAttribute`. The global advice enables declarative binding; the record is constructed via its canonical constructor.
- `POST /forms/profile` receives a **mutable JavaBean**. Local `@InitBinder("profile")` permits setter binding only for `displayName` and `city`.
- `admin` has a setter in the illustrative bean to prove the allowlist works: the client tries sending `admin=true`, yet the object retains `admin=false`.
- `BindingResult` sits immediately after the model attribute so the controller explicitly returns HTTP 400 when conversion/validation fails.
- `MockMvc` tests the shared contract, local exception, suppressed fields, and Bean Validation.

> Note: including `admin` in the form DTO and HTTP response is strictly for this security exercise. In production, **do not include privilege fields in input DTOs or demo responses**, and never trust the client to assert privileges.

### 7.1. Gradle and Structure

File `settings.gradle`:

```groovy
rootProject.name = 'shared-binder-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Directory layout:

```text
src/
  main/
    java/com/example/sharedbinder/
      SharedBinderApplication.java
      RegistrationForm.java
      ProfileForm.java
      SharedBindingAdvice.java
      FormsController.java
  test/
    java/com/example/sharedbinder/
      FormsControllerTest.java
```

`spring-boot-starter-web` includes Spring MVC, and `spring-boot-starter-validation` brings the Jakarta Bean Validation provider onto the classpath. The `-parameters` flag preserves parameter names when constructor binding needs reflection metadata. Java records carry their own metadata, yet this option remains useful for classes with data constructors.

### 7.2. Application

File `src/main/java/com/example/sharedbinder/SharedBinderApplication.java`:

```java
package com.example.sharedbinder;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SharedBinderApplication {

    public static void main(String[] args) {
        SpringApplication.run(SharedBinderApplication.class, args);
    }
}
```

### 7.3. `RegistrationForm`: Record and Constructor Binding

File `src/main/java/com/example/sharedbinder/RegistrationForm.java`:

```java
package com.example.sharedbinder;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record RegistrationForm(
        @NotBlank @Email String email,
        @NotNull @Min(18) Integer age
) {}
```

The record accepts only `email` and `age`. If a request also sends `admin=true`, the record has no matching constructor argument or setter. `@NotBlank`, `@Email`, `@NotNull`, and `@Min` are Jakarta Validation constraints; they run after binding when the controller requests `@Valid`.

### 7.4. `ProfileForm`: Mutable Bean Demonstrating Property Binding

File `src/main/java/com/example/sharedbinder/ProfileForm.java`:

```java
package com.example.sharedbinder;

import jakarta.validation.constraints.NotBlank;

public class ProfileForm {

    @NotBlank
    private String displayName;

    @NotBlank
    private String city;

    // Present solely to simulate mass-assignment risk.
    private boolean admin;

    public ProfileForm() {}

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public boolean isAdmin() {
        return admin;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }
}
```

This is a JavaBean with a no-arg constructor and public setters. Without property-binding control, `admin=true` could flow into `setAdmin`. In the example, the global binder policy and local allowlist prevent this. Never use real domain entities for form inputs.

### 7.5. `SharedBindingAdvice`: Shared Configuration Point

File `src/main/java/com/example/sharedbinder/SharedBindingAdvice.java`:

```java
package com.example.sharedbinder;

import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.InitBinder;

@ControllerAdvice
public class SharedBindingAdvice {

    @InitBinder
    public void initialize(WebDataBinder binder) {
        // Since Spring Framework 6.1:
        // Constructor binding is allowed.
        // Property binding only when allowedFields is declared.
        binder.setDeclarativeBinding(true);
    }
}
```

There is no need to call `initialize(...)` from controllers. Spring discovers `@ControllerAdvice` via component scanning and runs the initializer for matching binders. Advice classes are Spring singletons by default, but **each request/attribute gets its own `WebDataBinder`**; methods must never store request-specific binders in mutable singleton fields.

### 7.6. `FormsController`: Local `@InitBinder` Only for `profile`

File `src/main/java/com/example/sharedbinder/FormsController.java`:

```java
package com.example.sharedbinder;

import jakarta.validation.Valid;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/forms")
public class FormsController {

    // Runs after global @InitBinder for the attribute named "profile".
    @InitBinder("profile")
    void configureProfile(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "city");
    }

    @PostMapping(
        path = "/register",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<Map<String, Object>> register(
            @Valid @ModelAttribute("registration") RegistrationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return invalid(errors);
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("email", form.email());
        body.put("age", form.age());

        return ResponseEntity.status(HttpStatus.CREATED).body(body);
    }

    @PostMapping(
        path = "/profile",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<Map<String, Object>> profile(
            @Valid @ModelAttribute("profile") ProfileForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return invalid(errors);
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("displayName", form.getDisplayName());
        body.put("city", form.getCity());

        // Only to demo that admin=true was blocked.
        body.put("admin", form.isAdmin());

        // Only to demo how many fields the binder excluded from setter binding.
        body.put("suppressedCount", errors.getSuppressedFields().length);

        return ResponseEntity.ok(body);
    }

    private ResponseEntity<Map<String, Object>> invalid(
            BindingResult errors) {

        List<Map<String, String>> fields =
                errors.getFieldErrors().stream()
                    .map(error -> Map.of(
                            "field", error.getField(),
                            "code", Objects.toString(
                                    error.getCode(), "invalid")))
                    .sorted(Comparator.comparing(
                            field -> field.get("field")))
                    .toList();

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("code", "INVALID_FORM");
        body.put("fields", fields);

        return ResponseEntity.badRequest().body(body);
    }
}
```

Details to understand:

- The shared advice enables `setDeclarativeBinding(true)` on binders.
- For `"registration"`, there are no local `allowedFields`. Because the record has a canonical constructor, the binder can instantiate `RegistrationForm` via **constructor binding**. No public setters are needed.
- For `"profile"`, the local binder declares writable properties `displayName` and `city`. Once `allowedFields` is declared, declarative binding permits property binding for those fields.
- `@InitBinder("profile")` has no effect on `"registration"` because the attribute name differs.
- `@Valid` triggers Jakarta Bean Validation. `BindingResult` immediately following the attribute captures binding/validation errors if any occur.
- `admin` and `suppressedCount` appear in the **lesson's** response solely to observe the policy. A production API should not expose internal privileges or suppression details.
- Do not place class-level `@Validated` on the controller just for form binding; that is a separate mechanism (method validation) and can alter validation paths in Spring MVC 6.1+.

### 7.7. Trying with curl

Start once the project has a Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

**Form using a record:**

```bash
curl -i -X POST "http://localhost:8080/forms/register" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "email=lan@example.org" \
  --data-urlencode "age=22" \
  --data-urlencode "admin=true"
```

Expected HTTP: **201 Created**. Body:

```json
{
  "email": "lan@example.org",
  "age": 22
}
```

The input includes `admin`, but `RegistrationForm` does not declare it. Even so, do not design a record DTO with an `admin` parameter and expect the same policy to ignore sensitive values.

**Mutable form with a sensitive setter:**

```bash
curl -i -X POST "http://localhost:8080/forms/profile" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=Lan" \
  --data-urlencode "city=Hanoi" \
  --data-urlencode "admin=true"
```

Expected HTTP: **200 OK**. Illustrative body:

```json
{
  "displayName": "Lan",
  "city": "Hanoi",
  "admin": false,
  "suppressedCount": 1
}
```

The local allowlist contains only `displayName` and `city`; the binder does not call `setAdmin(true)` from property input. `getSuppressedFields()` shows that one field was blocked in this example. **Key takeaway:** blocked fields can be ignored without automatically creating validation errors; the demo endpoint still returns 200. If policy requires rejecting over-posting, add explicit handling.

**Bean Validation failure:**

```bash
curl -i -X POST "http://localhost:8080/forms/register" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "email=invalid" \
  --data-urlencode "age=22"
```

Expected result: **400 Bad Request**, with a response containing `code = INVALID_FORM` and a `field = email` entry with code `Email`.

**Numeric conversion failure:**

```bash
curl -i -X POST "http://localhost:8080/forms/register" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "email=lan@example.org" \
  --data-urlencode "age=abc"
```

In standard binder/record configuration, this request creates a binding error for `age` and HTTP 400 as the controller processes `BindingResult`. This is a type-conversion error, **not** the result of `@Min(18)`.

## 8. Integration Tests: Verifying Global and Local Policies Together

File `src/test/java/com/example/sharedbinder/FormsControllerTest.java`:

```java
package com.example.sharedbinder;

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
class FormsControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void immutableRecordUsesConstructorBinding() throws Exception {
        mvc.perform(post("/forms/register")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "lan@example.org")
                .param("age", "22")
                .param("admin", "true"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.email").value("lan@example.org"))
            .andExpect(jsonPath("$.age").value(22))
            .andExpect(jsonPath("$.admin").doesNotExist());
    }

    @Test
    void mutableFormAllowsOnlyNamedProperties() throws Exception {
        mvc.perform(post("/forms/profile")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Lan")
                .param("city", "Hanoi")
                .param("admin", "true"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.city").value("Hanoi"))
            .andExpect(jsonPath("$.admin").value(false))
            .andExpect(jsonPath("$.suppressedCount").value(1));
    }

    @Test
    void beanValidationStillRunsAfterBinding() throws Exception {
        mvc.perform(post("/forms/register")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "invalid")
                .param("age", "22"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_FORM"))
            .andExpect(jsonPath("$.fields[0].field").value("email"))
            .andExpect(jsonPath("$.fields[0].code").value("Email"));
    }

    @Test
    void invalidProfileFieldProducesValidationError()
            throws Exception {
        mvc.perform(post("/forms/profile")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", " ")
                .param("city", "Hanoi"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_FORM"))
            .andExpect(jsonPath("$.fields[0].field")
                    .value("displayName"));
    }

    @Test
    void validProfileWithoutExtraFieldStillWorks()
            throws Exception {
        mvc.perform(post("/forms/profile")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Mai")
                .param("city", "Hue"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.suppressedCount").value(0))
            .andExpect(jsonPath("$.admin").value(false));
    }
}
```

Run:

```bash
./gradlew test
```

**Expected:** all five tests PASS when the environment uses the Spring Boot 3.3.x, Java 17, and dependency configuration above. These tests verify behavior **through `DispatcherServlet`/`MockMvc`**, rather than manually instantiating `new ProfileForm()` and calling setters.

Meaning of each test case:

1. The record receives values via its constructor and has no `admin` property to emit.
2. Shared declarative binding does not block all mutable forms when a controller provides an allowlist.
3. `@Valid` still runs and returns field errors after binding.
4. Blank property input is caught by `@NotBlank` even when the field is allowlisted.
5. With no extra fields, no suppressed properties are recorded.

Do not assert error-list ordering when multiple errors exist. In the demo, `beanValidationStillRunsAfterBinding` and `invalidProfileFieldProducesValidationError` intentionally trigger only one invalid field, so `fields[0]` suffices. When forms can have multiple errors or varying locales, match by field/code rather than index position or message text.

### 8.1. Test the Policy Itself, Not Just HTTP Status

A **sufficiently thorough** test does more than assert HTTP 200 for valid forms. Intentionally submit sensitive property names and verify:

- The object does not receive `admin=true`.
- Fields in `allowedFields` still bind correctly.
- `BindingResult#getSuppressedFields()` reflects blocked fields where applicable.
- If the app chooses to reject over-posting, the status is 400 and no side effects occur.

Conversely, if you test only valid inputs and skip negative tests, a change such as deleting `@InitBinder("profile")` could slip through code review unnoticed.

## 9. What Can a Shared Binder Policy Customize?

### 9.1. Formatter or PropertyEditor

`@InitBinder` allows registering formatters locally or inside advice. Illustrative example:

```java
@ControllerAdvice
public class DateBindingAdvice {

    @InitBinder
    void customize(WebDataBinder binder) {
        binder.addCustomFormatter(new DateFormatter("yyyy-MM-dd"));
    }
}
```

This is an **independent alternative**, not a class to copy into the demo project unless you need date handling. `DateFormatter` lives in `org.springframework.format.datetime.DateFormatter`. It parses/formats `java.util.Date` by pattern; for `java.time.LocalDate`, use `@DateTimeFormat`/`DateTimeFormatterRegistrar` or an appropriate formatter in `ConversionService`.

If the entire application uses the same `LocalDate` convention, registering a formatter via `WebMvcConfigurer#addFormatters(FormatterRegistry)` or a shared `FormattingConversionService` is usually cleaner than adding unnecessary advice classes. If only one form has a custom rule, a local `@InitBinder` makes more sense.

For `PropertyEditor`, avoid sharing mutable instances across requests. `PropertyEditor` implementations are generally **not thread-safe**; create fresh instances per binder. Advice beans are typically singletons and must never store request-dependent formatters/editors in mutable fields.

### 9.2. Adding a Specialized Spring Validator

A custom Spring validator uses:

```java
org.springframework.validation.Validator
```

It differs from `jakarta.validation.Validator` in interface and error reporting. Spring's `Validator` defines `supports(Class<?>)` and `validate(Object, Errors)`.

Sample implementation:

```java
public class ProfileFormValidator
        implements org.springframework.validation.Validator {

    @Override
    public boolean supports(Class<?> type) {
        return ProfileForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        ProfileForm form = (ProfileForm) target;
        if ("root".equalsIgnoreCase(form.getDisplayName())) {
            errors.rejectValue("displayName", "reservedName");
        }
    }
}
```

This is an illustrative class; in a real project, import `org.springframework.validation.Errors` and `ProfileForm`. When registering:

```java
@InitBinder("profile")
void init(WebDataBinder binder) {
    binder.addValidators(new ProfileFormValidator());
}
```

Ensure the validator **supports the target type** before adding it; using global advice for all forms without checking `supports` can fail on incompatible objects. Also, `addValidators` **appends** validators whereas `setValidator`/`setValidators` can replace the configured set; avoid accidentally replacing the default Jakarta validator if you still rely on `@NotBlank` or `@Min`.

In practice, if a rule is a pure data constraint, a custom Jakarta `@Constraint` and `ConstraintValidator` are easier to reuse across multiple entrypoints. If the rule serves only MVC forms and depends on Spring `Errors`/field paths, a Spring `Validator` can be a good fit.

### 9.3. Limiting Nested/Collection Binding

`WebDataBinder`/`DataBinder` provides settings like `setAutoGrowNestedPaths(...)` and `setAutoGrowCollectionLimit(...)` controlling automatic expansion when binding indexed properties. For example:

```java
binder.setAutoGrowCollectionLimit(64);
```

This is an illustrative `@InitBinder` snippet, not a complete denial-of-service policy. When allowing request fields like `items[1000000].name` or deep object graphs, also bound request/collection sizes, validate element counts, and avoid overly broad wildcard allowlists.

### 9.4. What Does Not Belong in `@InitBinder`?

`@InitBinder` is not:

- An authentication/authorization filter.
- A mechanism to block all JSON properties before Jackson deserialization.
- A catch-all server exception handler.
- A transaction interceptor.
- A global validation pipeline running on every object instantiated manually in Java code.
- A safe place to hold shared data if mutable per-request state is stored in a singleton advice.

It is a **binder configuration hook for matching entrypoints and controllers**, not a substitute for input DTOs, service authorization, or database invariants.

## 10. `@ControllerAdvice` and `@ExceptionHandler`: Complementary Roles

Many projects have a `@RestControllerAdvice` for API errors. Depending on application size, you can combine or separate binder configuration classes:

```java
@RestControllerAdvice
public class ApiAdvice {

    @InitBinder
    void bind(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<Map<String, Object>> invalid(
            MethodArgumentNotValidException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "VALIDATION_ERROR"));
    }
}
```

This is an illustrative class, not part of the runnable project in section 7; it requires importing the annotations, HTTP types, and `MethodArgumentNotValidException`. The methods perform **two distinct jobs**:

- `@InitBinder` runs during binder initialization, **before binding/validation**.
- `@ExceptionHandler` runs after a matching exception is thrown, to build a response.

In our demo, the controller places `BindingResult` right after `@ModelAttribute`, so it **handles errors itself** and returns 400. Consequently, a global exception handler for `MethodArgumentNotValidException` would not receive errors from those endpoints; that does not mean the advice isn't working.

If `BindingResult` is omitted on standard MVC argument validation, Spring may throw `MethodArgumentNotValidException`. When a handler method has direct method constraints and MVC 6.1+ method validation applies, the exception may be `HandlerMethodValidationException`. Do not confuse these exceptions with binder configuration failures.

**Notable ordering rules:**

- Global `@InitBinder` runs **before** local `@InitBinder`.
- Local `@ExceptionHandler` takes precedence **before** global `@ExceptionHandler` when both match, per Spring's exception-resolution rules.
- Multiple `@ControllerAdvice` beans can be ordered with `@Order`/`Ordered`; if multiple advices modify the same binder field, explicitly test the final configuration. Never rely on ambiguous ordering to enforce security policies.

## 11. Differences with `@RequestBody` JSON and Multipart

### 11.1. `@ModelAttribute` Uses the Binder to Assign Properties

For:

```java
@PostMapping("/profile")
public void profile(@ModelAttribute ProfileForm form) { }
```

Spring MVC reads request parameters/form fields, creates the model object, runs constructor/property binding, and optionally validates afterwards. `setAllowedFields` affects **property binding** in this flow.

### 11.2. `@RequestBody` JSON Is Usually Handled by Jackson

For:

```java
@PostMapping("/profile-json")
public void profileJson(@RequestBody ProfileForm form) { }
```

Spring uses an `HttpMessageConverter`, usually Jackson, to deserialize JSON. Jackson has its own constructor/setter/property rules. A `WebDataBinder` may still be created for argument validation/error handling, but `setAllowedFields` does not act as a **JSON property allowlist** for Jackson.

Therefore, if a JSON endpoint receives:

```json
{
  "displayName": "Lan",
  "admin": true
}
```

and the JSON DTO still has a writable `admin` property, do not rely on global `@InitBinder#setAllowedFields` to stop Jackson from populating `admin`. Use **dedicated JSON input DTOs**, proper Jackson configuration, domain mapping, and server-side authorization.

### 11.3. `@RequestPart` JSON Metadata

`@RequestPart("metadata") SomeDto dto` in multipart requests typically goes through a message converter for the JSON part, behaving like `@RequestBody` for deserialization rather than turning `setAllowedFields` into a JSON filter. Conversely, ordinary form fields in multipart requests can still participate in `@ModelAttribute` binding per the controller signature.

In summary:

| Input | Primary Mechanism | Should You Rely on `allowedFields` to Block Extra Fields? |
| --- | --- | --- |
| Form/query `@ModelAttribute` mutable bean | `WebDataBinder` property binding | **Yes**, though dedicated DTOs are still preferred |
| Form/query `@ModelAttribute` record | Constructor binding | Does not alter the constructor parameter list |
| JSON `@RequestBody` | `HttpMessageConverter`/Jackson | **No**, use JSON DTOs/mappers |
| JSON part `@RequestPart` | Part converter | **No**, same as JSON body |
| File upload `MultipartFile` | Multipart resolver | Requires separate checks on file size/type/name/content |

This is one of the most critical security boundaries when configuring shared binders.

## 12. Does WebFlux Have `@ControllerAdvice` and `@InitBinder`?

Yes, Spring WebFlux annotated controllers also support `@ControllerAdvice` and `@InitBinder`, but the runtime is a **reactive stack** and binder/argument-resolution types differ. Do not copy all Servlet MVC code and assume every formatter, converter, exception, and threading behavior will match.

- In MVC, `DispatcherServlet` and `WebDataBinder` handle binding on the Servlet stack.
- In WebFlux, `DispatcherHandler`, codecs, and reactive binding mechanisms handle requests; `WebExchangeBindException` is the typical command-object binding/validation exception, unlike `MethodArgumentNotValidException` in MVC.
- WebFlux functional routes (`RouterFunction`) do not automatically invoke annotated controller `@InitBinder` methods the way controller `@ModelAttribute` arguments do.
- `@ControllerAdvice` can configure binders/exception handling for WebFlux annotated controllers, but tests should use `WebTestClient` rather than copying `MockMvc` when not running on Servlet.

This lesson focuses on Spring MVC because the runnable example uses `spring-boot-starter-web`. When deploying on WebFlux, consult the WebFlux documentation and adjust dependencies and tests accordingly.

## 13. Rolling Out a Global Binder Policy in a Running System

Setting `setDeclarativeBinding(true)` across all controllers is a **behavior-changing** modification, even though it is only a few lines of Java. Safe rollout plan:

1. **Inventory entrypoints** using `@ModelAttribute`, `form-urlencoded`, multipart form fields, or pre-populated model attributes.
2. **Classify inputs**: records/immutable DTOs, mutable form DTOs, directly bound JPA entities, existing session/model objects.
3. **Decouple from entities** wherever DTOs expose sensitive fields such as `role`, `owner`, `creditLimit`, `approved`, or `internalStatus`.
4. **Add explicit allowlists** on controllers with mutable forms that genuinely need setter binding.
5. **Scope the global advice appropriately** (application-wide, or by package/marker annotation) rather than enabling it blindly on an untested codebase.
6. **Run regression tests** covering valid inputs, missing fields, invalid types, extra fields, nested fields, and multipart requests.
7. **Monitor suppressed fields** in security-sensitive areas, optionally logging security events without sensitive field values.
8. **Audit JSON endpoints separately** because Jackson does not apply `allowedFields` like a property binder.
9. **Review global/local overrides** to prevent accidental `setDeclarativeBinding(false)` or `setAllowedFields("*")` calls from reopening binding.
10. **Deploy with rollback readiness**, watching for spikes in HTTP 4xx responses from blocked forms and business errors caused by missing inputs.
11. **Write contract tests** for fields that must be accepted, not just fields that must be blocked.
12. **Document your version baseline** because `declarativeBinding` requires Spring MVC 6.1+; older projects need a different strategy.

For a JSON-only API, address DTO/Jackson policies first; adding a global binder policy alone may not achieve the intended protection.

## 14. Common Mistakes and How to Fix Them

**Mistake 1 — Thinking `@ControllerAdvice` is only for catching exceptions.** It also shares `@InitBinder` and `@ModelAttribute`. An advice class without `@ExceptionHandler` is still valid and useful.

**Mistake 2 — Thinking `@RestControllerAdvice` runs only for `@RestController`.** By default it shares the same broad scope as `@ControllerAdvice`; use selectors if you want to restrict it.

**Mistake 3 — Confusing init-binder ordering with exception-handler ordering.** Global `@InitBinder` runs before local; conversely, local `@ExceptionHandler` takes priority for matching exceptions.

**Mistake 4 — Assuming a global policy cannot be overridden locally.** Setter calls on the same binder can affect the final configuration; treat code review and tests as part of security.

**Mistake 5 — Enabling `declarativeBinding` without preparing mutable forms.** Without an allowlist, setter binding will not run. This is intentional behavior, yet it can cause existing forms to drop fields.

**Mistake 6 — Using `setAllowedFields` to block sensitive constructor arguments.** Property-binding allowlists do not remove constructor parameters from a DTO. Remove those fields from the input contract.

**Mistake 7 — Using a denylist and assuming it stays safe.** New setters are easy to miss; explicit allowlists are the safer default.

**Mistake 8 — Using `@InitBinder("ProfileForm")` when `@ModelAttribute("profile")` is on the method.** The name must match the model attribute, not the class name.

**Mistake 9 — Believing `@InitBinder` applies to all JSON fields.** Jackson handles `@RequestBody`/JSON parts; `WebDataBinder` `allowedFields` is not a Jackson allowlist.

**Mistake 10 — Testing only HTTP status 200.** Also test bound field values, blocked fields, invalid types, constraint errors, nested properties, and side effects.

**Mistake 11 — Thinking suppressed fields automatically return 400.** Spring may ignore disallowed inputs and continue handling the request; add an explicit policy if you want to reject them.

**Mistake 12 — Registering a single-type custom validator globally.** Check `supports(Class<?>)` and target types to avoid breaking binders for other models.

**Mistake 13 — Placing mutable `PropertyEditor` instances in shared static/singleton state.** Mind thread safety; create per-binder editors or use thread-safe formatters/converters.

**Mistake 14 — Mixing Spring MVC with WebFlux.** MVC uses Servlets; WebFlux has separate handler/error APIs and should be tested with `WebTestClient`.

**Mistake 15 — Using `@Valid` to prevent over-posting.** Validation checks constraints after binding; it does not control which fields clients are allowed to set.

**Mistake 16 — Combining multiple selectors expecting AND.** `@ControllerAdvice` selectors combine with **OR**, easily widening scope unexpectedly.

**Mistake 17 — Storing request state in `@ControllerAdvice` instance fields.** Advice beans are usually singletons; mutable request-specific state causes race conditions and leaks. Use the binder and method arguments per request.

**Mistake 18 — Overlooking pre-existing data in Model/Session.** `@ModelAttribute` can bind onto an existing object rather than only a fresh one; allowlists are even more important to avoid mutating server state unexpectedly.

## 15. Decision and Design Checklist

| Question | Appropriate Approach |
| --- | --- |
| Need the same policy across multiple controllers? | `@ControllerAdvice` with `@InitBinder` |
| Only one controller needs an exception? | Local `@InitBinder`, optionally scoped by attribute name |
| Want constructor binding as the default? | `setDeclarativeBinding(true)` on Spring 6.1+ |
| Mutable form genuinely needs setters? | Explicit `setAllowedFields("fieldA", "fieldB")` |
| Want blocked fields to produce an error? | Check `getSuppressedFields()` and enforce rejection/logging policy |
| Want the same date format app-wide? | `WebMvcConfigurer#addFormatters` or shared `ConversionService` |
| Want the policy applied only to a controller package? | `@ControllerAdvice(basePackageClasses=...)` |
| Want the handler to process binding errors? | `BindingResult` next to the attribute, or `@ExceptionHandler` |
| Want security for JSON `@RequestBody`? | Input DTOs/Jackson/authorization, not just `allowedFields` |
| Want validation on valid fields? | `@Valid`/`@Validated` and Jakarta Validation provider |
| Want to protect admin/owner privileges? | Domain/service authorization and DTOs without privileged fields |
| Want to avoid breaking legacy forms during rollout? | Scoped advice, allowlists, `MockMvc` regression tests |

### Code Review Checklist

- Is `@ControllerAdvice` scanned by Spring with the right scope?
- Does the global configuration apply to all intended `@Controller` and `@RestController` beans?
- Does local configuration match the exact `@ModelAttribute` name?
- Does global `@InitBinder` execute before local `@InitBinder` as expected?
- Does any controller accidentally call `setDeclarativeBinding(false)` or use wildcard `allowedFields`?
- Does any input DTO expose sensitive fields in its constructor or writable properties?
- Are all legitimate input fields included in the local allowlist?
- Are `@Valid` or `@Validated(Group.class)` present where post-binding rules must run?
- Is `BindingResult` placed immediately after the target argument?
- Are there positive/negative tests for each input shape and error response?
- Are JSON endpoints evaluated independently of `WebDataBinder`?
- Does any code store mutable editors/binders in singleton advice state?

**Conclusion:** `@ControllerAdvice` lets you turn `@InitBinder` into a **shared binder configuration policy**, executed before local `@InitBinder` methods. A practical strategy in Spring MVC 6.1+ is enabling `setDeclarativeBinding(true)` as the baseline while permitting setter binding on mutable forms that truly need it via narrow `setAllowedFields(...)`. Ultimately, security comes from clean input DTOs, authorization checks, real request tests, and respecting the boundary between `@ModelAttribute` binding and Jackson `@RequestBody`. Never treat a global binder setting as proof that all inputs are protected.

## References

- [Spring Framework 6.2 — Controller Advice](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html): advice scope, global/local ordering, selectors.
- [Spring Framework 6.2 — @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html): binder configuration, formatters, `allowedFields`, and declarative binding.
- [Spring Framework 6.2 — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): constructor/property binding, `BindingResult`, and validation.
- [Spring Framework 6.2 — Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html): `DataBinder`, property paths, conversions, restrictions.
- [Spring Framework 6.2 — Web MVC Config](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config.html): shared conversion/formatting hooks.
- [Spring Framework — ControllerAdvice Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/bind/annotation/ControllerAdvice.html): OR-combined selectors, `Ordered`, and applicability scope.
