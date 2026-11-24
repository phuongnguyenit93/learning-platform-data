# Constructor Binding vs Property Binding in Spring MVC Controllers

## 1. One request, two ways to populate an object

When writing a Spring MVC controller, we often receive form data using `@ModelAttribute`:

```java
@PostMapping("/register")
public String register(@ModelAttribute RegistrationForm form) {
    // form has been bound from HTTP data.
    return "ok";
}
```

“Binding” is the process of converting HTTP values—typically strings—into Java properties with appropriate data types. For a model object, Spring supports two main mechanisms:

1. **Constructor binding:** takes input values matching constructor parameters, converts their types, and **instantiates the object via its constructor**. Very well suited for Java records and immutable DTOs.
2. **Property binding (setter binding):** takes an existing object or instantiates one, then **writes values into JavaBeans properties** via setters (and configured property access mechanisms).

Example request:

```http
POST /registrations
Content-Type: application/x-www-form-urlencoded

username=lan&age=21
```

You can create a record:

```java
public record RegistrationForm(String username, Integer age) {}
```

or bind into a bean with setters:

```java
public class RegistrationForm {
    private String username;
    private Integer age;

    public RegistrationForm() {}

    public void setUsername(String username) {
        this.username = username;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
```

Both styles can receive `username=lan` and `age=21`, but **how they are created and updated, their resistance to mass assignment, immutability, and how extra fields are handled** differ.

**Scope and versions:** this lesson focuses on Spring Framework 6.1–6.2, the Spring MVC Servlet stack, Spring Boot 3.x, and Java 17+. Spring MVC has version-specific additions: `@BindParam` and `setDeclarativeBinding` arrived in Spring Framework 6.1; constructor binding support for indexed collections/arrays was enhanced in 6.2. Do not apply every detail directly to Spring 5 or WebFlux without checking version-specific documentation.

## 2. Where does data binding fit in the Spring MVC pipeline?

A typical flow with `@ModelAttribute`:

```text
HTTP request
  |  query parameters, form fields, path variables
  v
DispatcherServlet
  |
  v
HandlerMethodArgumentResolver
  |  resolves the @ModelAttribute parameter
  v
Model attribute / WebDataBinder
  |  1. obtain existing object or construct a new one
  |  2. select constructor parameters and/or writable properties
  |  3. convert String to Integer, LocalDate, Enum...
  |  4. record binding/type mismatch errors
  |  5. if @Valid/@Validated is present, run Bean Validation
  v
Controller argument + BindingResult
  |  handle errors inline if BindingResult immediately follows attribute
  v
Controller method / response
```

**Do not confuse three concepts:**

- **Binding:** `"21"` → `Integer.valueOf(21)` passed to a constructor/setter.
- **Validation:** `@Min(18)` checks whether the converted value satisfies a constraint.
- **Business checks:** checking duplicate accounts, access permissions, transactions, or database state; these checks are not automatically guaranteed by binding or validation annotations alone.

In Spring MVC, `@ModelAttribute` is used with query parameters and form bodies. URI template variables can also be included as binding sources according to Spring's precedence rules. Spring Framework 6.2 further adds binding from HTTP headers; do not assume 6.1 has all of 6.2's header behavior. Request parameters take precedence over same-named path/header values in the modern MVC model.

A JSON request handled by `@RequestBody` goes through **HttpMessageConverter/Jackson** for deserialization; even though Jackson also has its own constructor/property semantics, that is **not** the `WebDataBinder` described here.

## 3. Constructor binding: defining inputs directly in the constructor

### 3.1. Concept and advantages

Constructor binding uses the parameters of a data constructor as the “list of accepted inputs”:

```java
public record RegistrationForm(
        String username,
        Integer age
) {}
```

With the pair `username=lan` and `age=21`, Spring MVC resolves parameter names, converts types, and calls the corresponding constructor:

```java
new RegistrationForm("lan", 21);
```

Record components are final; there are no setters to mutate `username` or `age` after creation. If a request also sends `role=ADMIN` and the record does not declare `role`, the record itself has nowhere to store that field.

Constructor binding **does not mean “every request is safe”**. If an input DTO constructor accepts a sensitive parameter such as `isAdmin`, it can still be bound from the request. Safety comes from **designing the allowed set of inputs**, not merely from the `record` keyword.

Common advantages:

- Expected inputs are explicitly listed in the constructor.
- Objects can be immutable; easy to reason about and test.
- No need for public setters on every property.
- Separates input DTOs from JPA entities/domain objects, reducing the risk of accidentally updating internal columns.
- Required values can be expressed via types and validation; constructors can enforce invariants when truly needed.

### 3.2. Which constructor is chosen?

Spring `DataBinder` supports objects with a single data constructor; when a class has multiple constructors, selection behavior depends on class structure. **A default no-arg constructor, if present, is typically chosen to construct the object**, after which property binding updates fields if permitted.

With a Java record, the canonical constructor clearly expresses the list of record components. With an immutable class, there should be one suitable constructor with **parameter names preserved in bytecode**. For regular classes, compiling with `-parameters` lets Spring read constructor argument names. If names are unavailable, Spring may fail to map `username`/`age` properly.

Gradle example:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
```

Do not think of `-parameters` as a way to “enable validation”: it primarily supplies parameter name metadata for reflection/binding. Java records preserve record component metadata; still keep consistent build settings for class-based DTOs.

### 3.3. Renaming inputs with @BindParam

Since Spring Framework 6.1, `@BindParam` allows the request parameter name to differ from the constructor parameter name. The following is an **illustrative class**:

```java
import org.springframework.web.bind.annotation.BindParam;

public class CustomerInput {
    private final String firstName;

    public CustomerInput(
            @BindParam("first-name") String firstName) {
        this.firstName = firstName;
    }

    public String getFirstName() {
        return firstName;
    }
}
```

Input `first-name=Lan` can be mapped to the `firstName` parameter. `@BindParam` belongs to **Spring**, not Jakarta Validation, not Jackson `@JsonProperty`, and not `@RequestParam`. It can also be placed on the field corresponding to a constructor parameter; additionally, `DataBinder.NameResolver` supports custom name-mapping strategies.

**Distinction:** `@JsonProperty("first_name")` typically controls Jackson JSON serialization/deserialization, whereas `@BindParam("first-name")` serves Spring `@ModelAttribute` constructor binding. Do not assume one annotation automatically replaces the other.

### 3.4. Unconvertible values

If a request passes:

```text
username=lan&age=abc
```

`"abc"` cannot be validly converted to `Integer`. Spring records a **type mismatch/conversion error** in `BindingResult` or triggers the exception path when the controller does not accept errors inline. It does not silently turn `abc` into `0` to bypass checks.

The `@Min(18)` constraint runs **after binding and type conversion** succeed. A conversion error is not a `@Min` violation; the frontend needs to distinguish “must enter a number” from “number must be large enough”.

## 4. Property binding: instantiate then assign via properties

### 4.1. JavaBeans properties

A mutable object typically has a no-arg constructor and setters:

```java
public class ProfileForm {
    private String displayName;
    private Integer age;

    public ProfileForm() {}

    public void setDisplayName(String value) {
        this.displayName = value;
    }

    public void setAge(Integer value) {
        this.age = value;
    }

    public String getDisplayName() {
        return displayName;
    }

    public Integer getAge() {
        return age;
    }
}
```

With request `displayName=Lan&age=23`, property binding executes logic equivalent to:

```java
ProfileForm input = new ProfileForm();
input.setDisplayName("Lan");
input.setAge(23);
```

Benefits:

- Fits mutable forms and traditional JavaBeans projects.
- Can be applied to an **already existing** object in the model or session.
- Supports nested structures, collections, or indexed paths within data and binder configuration limits.
- Easy to integrate with form editing, where an object needs deliberate updates.

Major drawback: if the object exposes additional public setters for sensitive fields, a request can intentionally submit those property names.

### 4.2. Mass assignment: the risk of binding “every setter”

Consider an entity containing:

```java
public class Account {
    private String displayName;
    private boolean admin;

    public void setDisplayName(String name) {
        this.displayName = name;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }
}
```

If you bind the request directly onto `Account` without restricting which properties may be modified, the input:

```text
displayName=Lan&admin=true
```

can mutate the `admin` property unintentionally. This is **mass assignment/over-posting**, a security issue rather than a Bean Validation error. Adding `@NotNull` or `@Valid` **does not automatically prevent** updating sensitive properties.

The priority order should usually be:

1. **Use dedicated DTOs per endpoint**, containing only data clients are allowed to supply.
2. Prefer **constructor binding + immutable input** when suitable.
3. If property binding is needed, set a specific **`allowedFields` allowlist**.
4. Convert the DTO to domain/entity objects in the service layer, applying authorization and business rules before writing to the database.

## 5. Both mechanisms can operate together in one @ModelAttribute

This is an easily overlooked point: Spring MVC **by default can perform both constructor binding and property binding** while creating/populating a model attribute.

This means:

- When a new object is needed, Spring can construct it via a data constructor or a no-arg constructor.
- Afterward, if writable properties exist and are not restricted, the binder can still set properties from the request.
- On an immutable record, components have no setters, so property binding cannot update them.
- On a mutable bean, property binding may update more fields than business logic actually intends to accept.
- If a model attribute is retrieved from `Model`/`@SessionAttributes` or pre-created by a `@ModelAttribute` method, the object already exists; property binding onto an existing object must be reviewed carefully.

Spring Framework 6.1 provides:

```java
binder.setDeclarativeBinding(true);
```

In this mode, **constructor binding still runs**, while **property binding runs only when `allowedFields` is configured**. This provides a general safeguard so data binding follows an explicit input structure.

Example:

```java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

This method snippet is illustrative inside a controller or `@ControllerAdvice`, requiring imports for `org.springframework.web.bind.WebDataBinder` and `org.springframework.web.bind.annotation.InitBinder`. When configured controller-wide, make sure endpoints using mutable forms do not unexpectedly stop binding properties; the solution is to define explicit allowlists or migrate to immutable DTOs.

**Crucial warning:** `setAllowedFields(...)` governs **property binding**, not a filter that disables constructor parameters. If an input constructor has `admin`, setting a property allowlist of only `displayName` will not block `admin` in constructor binding. Design constructor DTOs without sensitive inputs from the start.

## 6. Overview comparison table

| Criterion | Constructor binding | Property binding |
| --- | --- | --- |
| Binding target | Constructor parameters | JavaBeans setters/writable properties |
| New object | Instantiates object with converted values | Can instantiate empty object then update properties |
| Suitable types | Records, immutable DTOs, classes with data constructors | Mutable forms/JavaBeans |
| Considered fields | Constructor parameter names | Writable property paths |
| Extra fields | Without a matching constructor param, cannot become a constructor argument | Can be set if property is writable and not blocked |
| Renaming inputs | `@BindParam` | JavaBeans property name / custom binder config |
| Existing object in model | Not the typical “create new” path | Can update an existing object |
| Safe configuration | Declare only allowed inputs in constructor; `declarativeBinding` | Dedicated DTOs, `allowedFields`, avoid binding entities |
| Nested structures | Supported via constructors, with version-dependent enhancements | Via nested/indexed property paths |
| Conversion errors | Recorded in `BindingResult` | Recorded in `BindingResult` |
| Jakarta Bean Validation | Checked after binding with `@Valid`/`@Validated` | Same |
| Pitfalls to avoid | Constructor containing security attributes clients shouldn't supply | Unrestricted sensitive setters |

Both forms use `WebDataBinder` to manage conversions, errors, and optionally trigger validation. Do not assume that “using `@ModelAttribute` always means property binding” or “having a constructor stops Spring from touching setters”.

## 7. Runnable Spring Boot example: two endpoints, two input styles

The small project below includes:

- `POST /binding/registrations`: immutable record and constructor binding.
- `POST /binding/profiles`: mutable bean and property binding with an allowlist.
- Validation using Jakarta `@NotBlank`, `@NotNull`, and `@Min`.
- `BindingResult` immediately after `@ModelAttribute` so the controller returns a structured HTTP 400.
- HTTP testing with `MockMvc`, including attempting to send a disallowed `privileged=true` property.

### 7.1. Dependencies and directory structure

File `settings.gradle`:

```groovy
rootProject.name = 'mvc-binding-demo'
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

`spring-boot-starter-web` provides Spring MVC and Jackson; `spring-boot-starter-validation` provides Jakarta Bean Validation with a Spring Boot-managed provider. This article uses Spring Boot 3.3.x (Spring Framework 6.1.x).

Structure:

```text
src/
  main/java/com/example/mvcbinding/
    MvcBindingApplication.java
    RegistrationForm.java
    ProfileForm.java
    BindingController.java
  test/java/com/example/mvcbinding/
    BindingControllerTest.java
```

### 7.2. Application

`src/main/java/com/example/mvcbinding/MvcBindingApplication.java`:

```java
package com.example.mvcbinding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcBindingApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcBindingApplication.class, args);
    }
}
```

### 7.3. Record for constructor binding

`src/main/java/com/example/mvcbinding/RegistrationForm.java`:

```java
package com.example.mvcbinding;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record RegistrationForm(
        @NotBlank String username,
        @NotNull @Min(18) Integer age
) {}
```

The record has two components corresponding to the two canonical constructor parameters. Jakarta annotations are used for post-binding validation; no setters are needed.

`@Min(18)` does not forbid `null` under the Bean Validation contract. Therefore `@NotNull` is placed alongside it on `age`. `@NotBlank` rejects null, empty, or whitespace-only strings.

### 7.4. JavaBean for property binding

`src/main/java/com/example/mvcbinding/ProfileForm.java`:

```java
package com.example.mvcbinding;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class ProfileForm {

    @NotBlank
    private String displayName;

    @NotNull
    @Min(18)
    private Integer age;

    // Intentionally includes a sensitive setter to test the allowlist.
    private boolean privileged;

    public ProfileForm() {}

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }

    public boolean isPrivileged() {
        return privileged;
    }

    public void setPrivileged(boolean privileged) {
        this.privileged = privileged;
    }
}
```

In a real system, you should **remove `privileged` entirely from the input DTO** and not return it in the response. This example intentionally includes this setter to prove that `allowedFields` blocks a request field that JavaBeans property binding would otherwise assign if left unrestricted.

### 7.5. Controller: configuring binders by attribute name

`src/main/java/com/example/mvcbinding/BindingController.java`:

```java
package com.example.mvcbinding;

import jakarta.validation.Valid;
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
@RequestMapping("/binding")
public class BindingController {

    @InitBinder("registration")
    void registrationBinder(WebDataBinder binder) {
        // Enable constructor binding; disallow property binding
        // unless allowedFields is declared.
        binder.setDeclarativeBinding(true);
    }

    @InitBinder("profile")
    void profileBinder(WebDataBinder binder) {
        // Mutable bean: allow only these two properties.
        binder.setAllowedFields("displayName", "age");
    }

    @PostMapping(
        path = "/registrations",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<Map<String, Object>> register(
            @Valid @ModelAttribute("registration") RegistrationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return invalid(errors);
        }

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("username", form.username());
        response.put("age", form.age());

        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @PostMapping(
        path = "/profiles",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<Map<String, Object>> updateProfile(
            @Valid @ModelAttribute("profile") ProfileForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return invalid(errors);
        }

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("displayName", form.getDisplayName());
        response.put("age", form.getAge());
        response.put("privileged", form.isPrivileged());

        return ResponseEntity.ok(response);
    }

    private ResponseEntity<Map<String, Object>> invalid(
            BindingResult result) {

        List<Map<String, String>> fields = result.getFieldErrors()
                .stream()
                .map(error -> Map.of(
                        "field", error.getField(),
                        "code", Objects.toString(
                                error.getCode(), "invalid")
                ))
                .toList();

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("errors", fields);
        return ResponseEntity.badRequest().body(response);
    }
}
```

Key points in the controller:

- `@ModelAttribute("registration")` clarifies the model attribute name so `@InitBinder("registration")` applies to the right object.
- `setDeclarativeBinding(true)` applies only to `registration`; our record has a constructor taking exactly `username` and `age`.
- `@ModelAttribute("profile")` pairs with `@InitBinder("profile")`, allowing property binding **only** for `displayName` and `age`.
- `BindingResult errors` sits **immediately after** the `@Valid @ModelAttribute` parameter. If a binding/validation error occurs, the controller handles it instead of letting the default exception path run.
- The demo response includes `privileged` so you can observe the security restriction working. In a production API, do not expose an internal privilege field just for debugging; actual permissions must also be verified in the service layer.
- The error map returns `field` and `code` so tests do not depend on the language of default messages. In a production API, you can standardize custom error codes more stable than `FieldError#getCode()`.

### 7.6. Sending form requests

Start the app:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

**Successful constructor binding:**

```bash
curl -i -X POST "http://localhost:8080/binding/registrations" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "username=lan" \
  --data-urlencode "age=21"
```

Expected HTTP `201 Created`, JSON body (key order is not part of the API contract):

```json
{
  "username": "lan",
  "age": 21
}
```

**Property binding with a request attempting privilege escalation:**

```bash
curl -i -X POST "http://localhost:8080/binding/profiles" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=Lan" \
  --data-urlencode "age=23" \
  --data-urlencode "privileged=true"
```

Expected HTTP `200 OK` and JSON:

```json
{
  "displayName": "Lan",
  "age": 23,
  "privileged": false
}
```

`privileged=true` was present in the request but not in `allowedFields`, so `setPrivileged(true)` was not called via property binding. In the example, the boolean stays at its default `false`.

**Conversion error:** send `age=abc`:

```bash
curl -i -X POST "http://localhost:8080/binding/registrations" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "username=lan" \
  --data-urlencode "age=abc"
```

Expected HTTP `400 Bad Request` with an error associated with field `age`; `code` may be `typeMismatch` or a code determined by the binder/exception adapter. Do not make tests depend on a specific localized message in this case.

## 8. Integration tests: verifying constructor, setters, and allowlist

`src/test/java/com/example/mvcbinding/BindingControllerTest.java`:

```java
package com.example.mvcbinding;

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
class BindingControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void recordIsConstructedFromRequestParameters() throws Exception {
        mvc.perform(post("/binding/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("username", "lan")
                .param("age", "21")
                .param("privileged", "true"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.username").value("lan"))
            .andExpect(jsonPath("$.age").value(21))
            .andExpect(jsonPath("$.privileged").doesNotExist());
    }

    @Test
    void recordValidationDetectsUnderage() throws Exception {
        mvc.perform(post("/binding/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("username", "lan")
                .param("age", "16"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].field").value("age"));
    }

    @Test
    void propertyBindingAllowsOnlyExplicitFields() throws Exception {
        mvc.perform(post("/binding/profiles")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Lan")
                .param("age", "23")
                .param("privileged", "true"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.age").value(23))
            .andExpect(jsonPath("$.privileged").value(false));
    }

    @Test
    void invalidNumberProducesBindingError() throws Exception {
        mvc.perform(post("/binding/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("username", "lan")
                .param("age", "abc"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors").isArray());
    }
}
```

Run tests:

```bash
./gradlew test
```

These tests cover the key differences: the record has no `privileged` component, the mutable bean still has a sensitive setter but is protected by the allowlist, `@Min(18)` runs after binding, and type conversion errors produce a `400` response.

**Assertion caveat:** the sample has only one invalid constraint in the `age=16` test, so checking `errors[0]` is reasonable. In projects with multiple errors, `BindingResult#getFieldErrors()` or constraint violations from the provider may not have a deterministic order; look up errors by field/code instead of assuming first position.

### 8.1. Testing suppressed fields further via BindingResult

Spring `BindingResult` provides `getSuppressedFields()`, allowing you to inspect field names blocked by `allowedFields`/`disallowedFields`. In integration tests you can use a dedicated logger/test hook or directly unit-test `DataBinder`; **do not expose internal property names in production responses** just to prove a field was blocked.

Conceptual API example (illustrative snippet inside a handler with `BindingResult result`):

```java
String[] suppressed = result.getSuppressedFields();
```

With input `privileged=true` and an allowlist of only `displayName` and `age`, `privileged` can appear in the suppressed list. Being suppressed **does not automatically produce a Bean Validation error** like `@NotBlank`; if you want to treat an over-posting attempt as a security event, handle/log it at the appropriate layer.

## 9. @InitBinder and WebDataBinder: scoping restrictions properly

### 9.1. Controller-level binder

`@InitBinder` receives `WebDataBinder` and lets you configure type conversion, field allowlists, declarative binding, formatters, and validators per request:

```java
@InitBinder("profile")
void initProfile(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "age");
}
```

This is an illustrative controller method; `"profile"` must match the model attribute name being bound. If the model attribute has a different name, the scoped configuration may not run as expected.

Never take untrusted property names from a request to build a dynamic allowlist. The list of allowed fields should be defined by the endpoint's contract.

### 9.2. Shared binder across controllers

A configuration can use `@ControllerAdvice`:

```java
@ControllerAdvice
public class GlobalBindingPolicy {

    @InitBinder
    public void restrictBinding(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
```

This is an **alternative configuration**; do not add it verbatim to the demo project without checking its impact on `ProfileForm`. When declarative binding is enabled application-wide, traditional forms relying purely on setters without `allowedFields` may stop binding as before.

The goal of `setDeclarativeBinding(true)` is not to “disable all binding”, but to **default to constructor binding only**, allowing property binding only when `allowedFields` is declared. If mutable endpoints are needed, apply explicit allowlists and write regression tests.

### 9.3. Allowed fields vs disallowed fields

Spring supports:

```java
binder.setAllowedFields("displayName", "age");
```

and:

```java
binder.setDisallowedFields("admin", "role");
```

However, **an allowlist is preferred** because it is explicit: adding a new `approved` or `creditLimit` setter to a domain object will not automatically allow it. A denylist requires tracking every sensitive field and easily misses additions during schema changes.

Allowlists can also specify property paths such as `address.city`, `items[0].sku`, or wildcards when truly needed. Beware of overly broad wildcards, especially on nested objects, as they may open unexpected paths.

### 9.4. @ModelAttribute(binding=false)

If a controller receives an object already placed in the Model, sometimes you only want to read it **without applying request parameters onto it**:

```java
@GetMapping("/preview")
public String preview(
        @ModelAttribute(binding = false) Account account) {
    // Use the model attribute prepared from a trusted source.
    return "preview";
}
```

This is an illustrative controller method, not a complete object-loading flow. `binding = false` prevents data binding for that model attribute; ensure the object is created/provided to the controller through proper logic. It does not replace authorization when fetching an entity from the database.

## 10. Nested objects, collections, and property paths

### 10.1. Path-based property binding

With a bean containing `Address address` that has a getter/setter, a form can use names:

```text
address.city=Hanoi
address.zipCode=100000
```

Spring can traverse property paths and instantiate/assign nested objects according to binder configuration, converters, and object-graph auto-grow capabilities. With collections, paths may look like:

```text
items[0].sku=SKU-1
items[1].sku=SKU-2
```

These are common property path naming conventions; runnable code also requires the corresponding classes, constructors, setters, and collection declarations. Do not assume every nested/list structure is instantiated automatically for every DTO.

**Security:** allowlists must also consider nested paths. Blocking `admin` at the top level while allowing an overly broad wildcard like `account.*` can expose sensitive setters on child objects. Limit collection/auto-grow sizes and element counts per application policy to prevent huge requests from exhausting resources.

### 10.2. Constructor binding for nested objects and collections

Constructor binding supports nested objects through constructors on child types. Spring Framework 6.2 significantly expanded constructor binding support for `List`, `Map`, and arrays using indexed request keys, such as `accounts[0].name`. If you are on Spring Boot 3.3 (Spring 6.1) like the demo, **do not assume all 6.2 collection constructor binding features are present**.

For an endpoint needing complex nested lists, check your Spring version and write tests with real requests. Some data models are better suited to a JSON body via `@RequestBody`, provided the API design and security policy allow it.

## 11. Type conversion, validation, and errors: three layers of checks

| Input | Error stage | Actual outcome |
| --- | --- | --- |
| `age=21` for `Integer` | None | String converted to number 21 |
| `age=abc` for `Integer` | Binding/conversion | `typeMismatch` or binding error |
| `age=16` with `@Min(18)` | Bean Validation | Converted value is below threshold |
| `username=` with `@NotBlank` | Bean Validation | Blank string is invalid |
| `privileged=true` blocked by `allowedFields` | Property binding policy | Field is suppressed, not a `@NotBlank` violation |
| Input for nonexistent property | Binding policy | Depends on binder `ignoreUnknownFields` and custom handling |
| Input assigning internal-only field in constructor DTO | Flawed DTO design | Setter allowlist cannot fix this |

### 11.1. Registering Formatters/Converters

If a request includes `birthday=2026-01-02` and the DTO has a `LocalDate`, Spring needs a compatible formatter/converter. Annotation example:

```java
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
private LocalDate birthday;
```

This is a snippet inside a bean requiring `java.time.LocalDate` and `org.springframework.format.annotation.DateTimeFormat`; it is not a complete application. With constructor parameters, conversion metadata must also be declared/registered where Spring can read it. Do not parse date strings manually inside setters when a uniformly configured `FormattingConversionService` can handle it.

`@InitBinder` can also register a `PropertyEditor` or `Formatter`, though shared formatters/converters are usually cleaner when many endpoints use the same types. When conversion fails, the error is a binding error, not automatically a validation constraint error.

### 11.2. BindingResult must immediately follow the right attribute

Correct:

```java
public String save(
        @Valid @ModelAttribute("profile") ProfileForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "profile-form";
    }
    return "success";
}
```

Incorrect or misleading:

```java
public String save(
        @Valid @ModelAttribute("profile") ProfileForm form,
        @RequestParam String source,
        BindingResult errors) {
    return "success";
}
```

These are two controller method snippets, not standalone programs. `BindingResult` must appear **immediately after** the corresponding model attribute parameter; inserting another parameter in between prevents Spring from associating a valid binding result with that attribute.

If `BindingResult` is omitted, Spring MVC may throw `MethodArgumentNotValidException` when validation on `@ModelAttribute` itself fails; when an endpoint also has direct method constraints, Spring MVC 6.1+ uses a separate method validation path and may throw `HandlerMethodValidationException`. Do not equate every binding/conversion failure with a single exception type across all configurations.

### 11.3. @Valid is not triggered automatically by constructors

Constructor binding only instantiates an object. `@NotBlank` and `@Min` do not automatically execute just because a constructor is invoked via reflection. In an annotated controller, `@Valid` or `@Validated` (with groups when needed) instructs the framework to validate the object after binding.

Similarly, `@Valid` does not forbid a request field `privileged=true` if the property is writable: that is the domain of data binding policy. Enforce input security policies and business authorization **before** trusting successfully bound data.

## 12. @RequestBody vs @ModelAttribute: do not mix the two models

Example of two endpoints:

```java
@PostMapping("/form")
public void form(@Valid @ModelAttribute RegistrationForm form) {
    // MVC DataBinder: request parameters, form/query.
}

@PostMapping("/json")
public void json(@Valid @RequestBody RegistrationForm form) {
    // HttpMessageConverter / Jackson: JSON body.
}
```

These are controller method snippets, not a complete class. Both create a `RegistrationForm` and can run Bean Validation, but **their data-reading pipelines differ**.

| Aspect | @ModelAttribute | @RequestBody |
| --- | --- | --- |
| Common inputs | Query string, HTML form-urlencoded, multipart form | JSON/XML and body media types supported by converters |
| Primary mechanism | Spring MVC `WebDataBinder` | `HttpMessageConverter`, typically Jackson for JSON |
| Constructor/property in this lesson | Spring `DataBinder` | Jackson has its own object construction/assignment mechanism |
| `@InitBinder#setAllowedFields` | Applies to property binding | Not a protection mechanism for Jackson JSON |
| `@BindParam` | Names a Spring constructor parameter | Does not replace `@JsonProperty` |
| Validation | `@Valid`/`@Validated` after binding | `@Valid`/`@Validated` after deserialization |
| Input conversion failure | Binding error/`BindingResult` | Typically `HttpMessageNotReadableException` for unparseable JSON |

If an API receives JSON, protect inputs with dedicated JSON DTOs, appropriate Jackson annotations, and service-layer authorization; do not just configure `WebDataBinder`'s `allowedFields` and assume all JSON fields are blocked.

## 13. Common implementation mistakes

**1. Thinking records only use constructor binding and need no input design.** If a record declares `boolean admin`, a client can still send that value for Spring to pass to the constructor. Keep sensitive fields out of DTOs.

**2. Using a JPA entity directly as `@ModelAttribute`.** Entities often expose many setters for internal state. If binding directly is unavoidable, use a strict allowlist or switch to a DTO. Always control ID, owner, role, and status in the service layer.

**3. Thinking `setAllowedFields` also restricts constructor parameters.** It primarily restricts property binding; constructors still accept their declared parameters. Use input DTOs containing only permitted inputs.

**4. Adding `@Valid` and assuming mass assignment is blocked.** Validation checks constraints on the object; it does not protect writable properties from unexpected inputs.

**5. Missing constructor parameter names in bytecode.** For non-record classes, parameter name metadata or `@BindParam` is needed; otherwise binding may fail or fail to map as expected.

**6. Adding setters to fix a constructor binding error without considering security.** Adding setters can open up property binding for matching request names. Check the constructor and parameter name metadata first.

**7. Calling a type mismatch a `@Min` error.** `age=abc` is not a number below the minimum. Distinguish conversion errors from Bean Validation violations to return clear messages.

**8. Placing `BindingResult` non-adjacently to `@ModelAttribute`.** Spring requires it immediately after the validated argument when handling errors inline.

**9. Enabling `setDeclarativeBinding(true)` app-wide without updating mutable form endpoints.** Property binding will stop applying unless an allowlist is set; run regression tests.

**10. Using a denylist and forgetting to add newly introduced sensitive properties.** `disallowedFields` does not evolve safely as models grow; prefer `allowedFields`.

**11. Confusing `@ModelAttribute` with `@RequestBody`.** One uses MVC DataBinder and request parameters; the other typically uses Jackson deserialization of JSON.

**12. Applying Spring 6.2 docs to a Spring 6.1 runtime.** Features added in 6.2 (such as complex collection constructor binding support) are not automatically available in Spring Boot 3.3. Always check your BOM/runtime dependencies.

**13. Assuming a suppressed field produces HTTP 400 by default.** The binder can ignore disallowed fields and continue processing. If policy requires rejecting or logging a security event, write explicit handling.

**14. Relying on binding to enforce database invariants.** Conditions depending on existing data, authorization, and transactions must be checked in the service/domain layer, not during object creation.

## 14. Secure controller design checklist

1. Determine whether the endpoint actually accepts **form/query** (`@ModelAttribute`) or **JSON** (`@RequestBody`).
2. Define **dedicated input DTOs**; do not bind directly onto domain/JPA entities.
3. Prefer Java records or immutable constructor DTOs when inputs form a fixed set of values.
4. When using class constructors, preserve runtime parameter names (`-parameters` or `@BindParam`).
5. When using mutable forms, configure `@InitBinder#setAllowedFields(...)` with a specific property list.
6. To disable default setter binding, use `setDeclarativeBinding(true)` (Spring 6.1+) and audit existing endpoints.
7. Never include role/admin/owner/internal status in input constructor DTOs or public writable setters.
8. Register tested converters/formatters; distinguish type conversion errors from validation errors.
9. Place `@Valid`/`@Validated` and `BindingResult` in the proper positions to handle invalid data.
10. Test valid requests, missing required fields, wrong types, extra fields, sensitive fields, and nested/collection cases if used.
11. Test real requests with `MockMvc`, rather than only calling constructors/JavaBean setters directly in unit tests.
12. Map DTO → domain in the service layer, enforcing permissions, consistency, and business invariants when updating state.

### Conclusion

**Constructor binding** expresses accepted inputs directly in constructor parameters and suits immutable DTOs. **Property binding** operates through writable JavaBeans properties—flexible, yet requiring allowlists to prevent over-posting. In Spring MVC, **both can apply together to `@ModelAttribute`** unless declarative binding is configured or the object design omits setters. Keep HTTP inputs, type conversion, validation, and business authorization distinct; a successfully bound object does not mean all of its values are safe to use.

## References

- [Spring Framework — MVC Data Binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html): binding styles, object design, and security.
- [Spring Framework — @ModelAttribute method arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): how MVC constructs model attributes, constructor/property binding, and `BindingResult`.
- [Spring Framework — Core Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html): `DataBinder`, conversion, and property/constructor behavior.
- [Spring Framework — @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html): `allowedFields` and `declarativeBinding`.
- [Spring Framework — @BindParam Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/bind/annotation/BindParam.html): constructor parameter naming in MVC.
