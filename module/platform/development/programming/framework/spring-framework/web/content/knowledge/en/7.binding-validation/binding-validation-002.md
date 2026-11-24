# Constructor Binding, Property Binding, and Input DTO Design in Spring MVC

## 1. The Problem: How Do We Turn HTTP Data into Java Objects?

When a client sends a query string, an HTML form, or certain values from path/headers, Spring MVC can populate a Java object through **data binding**. The two main paths are:

- **Constructor binding:** uses input values to invoke a constructor and create a new object. Constructor parameter names and types explicitly express what data is allowed to be supplied.
- **Property binding (setter binding):** creates or retrieves an existing object, then uses setters/JavaBeans properties to assign values. Without restricting allowed fields, a client might modify properties that the developer never intended to expose to requests.

This lesson focuses on **`@ModelAttribute`, `WebDataBinder`, and request DTO design in Spring Web MVC (Servlet stack)**. JSON `@RequestBody` is contrasted separately because its object creation mechanism differs. Examples run on **Java 17, Spring Boot 3.3.5 (Spring Framework 6.1.x)**; the `@BindParam` and `setDeclarativeBinding` APIs were introduced in Spring Framework 6.1.

An HTTP form request may look like:

```http
POST /api/registration HTTP/1.1
Content-Type: application/x-www-form-urlencoded

email=lan%40example.com&age=21
```

Spring initially receives values as strings, such as `"21"`, then uses `WebDataBinder`'s type converters to produce the property `int age = 21`. If `age=abc` is sent, Spring cannot convert that string to `int` and records an error in `BindingResult`.

> **Important distinction:** `@ModelAttribute` typically binds from request parameters (query/form), and in appropriate cases also from URI variables/request headers; `@RequestBody` reads the body via `HttpMessageConverter`, usually using Jackson when the body is JSON. Both can accept a DTO, but **you must not assume their binding mechanisms and whitelist rules are the same**.

## 2. The Processing Flow of @ModelAttribute

Below is the high-level path in Spring MVC:

```text
Client sends form/query/path/header
      |
DispatcherServlet locates handler method
      |
Argument resolver processes @ModelAttribute
      |
Find object in model or create new object
      |-- Constructor binding: map parameters -> constructor
      |-- Property binding: map property names -> setters
      |
WebDataBinder converts String to Java types
      |
Validation (if @Valid/@Validated and Validator are present)
      |
BindingResult records binding/validation errors
      |
Controller receives bound DTO
```

Depending on the situation, `@ModelAttribute` can also reference an object already present in the model or session rather than always creating a new one. By default, Spring MVC allows **both constructor binding and property binding** where applicable; using a constructor does not automatically disable all setters.

Example:

```java
@PostMapping("/search")
public String search(@ModelAttribute SearchCriteria criteria) {
    return "search";
}
```

This is a controller illustration, not a standalone Java program. Spring attempts to create or retrieve `SearchCriteria` and bind data into the object. For complex parameter types not handled by another resolver, Spring MVC can infer `@ModelAttribute` implicitly; **explicitly writing the annotation is recommended** for readability and AOT tooling clarity.

### Binding Differs from Validation

| Step | Question it answers | Example |
| --- | --- | --- |
| Constructor/property binding | Which field does a request value go into, and by what mechanism? | `age=21` is assigned to `int age` |
| Type conversion | Does the type conversion succeed? | `"abc"` cannot be converted to `int` |
| Bean Validation | Does the converted value satisfy constraints? | `@Min(18)` rejects `age=16` |
| Business validation/authorization | Does the user have permission and do business rules allow it? | User A cannot change User B's role |

`@Valid` does not restrict which fields can be assigned; `setAllowedFields` does not prove data is valid under business rules. These are separate responsibilities.

## 3. Constructor Binding: Immutable DTOs

With Java 17+, `record` is a natural choice for a DTO that receives values once:

```java
public record RegistrationForm(
        @NotBlank @Email String email,
        @Min(18) int age
) {}
```

This declaration requires imports `jakarta.validation.constraints.NotBlank`, `Email`, and `Min`, along with the validation starter. When Spring binds `email=lan%40example.com&age=21`, it extracts both parameters, converts `age` to `int`, invokes the record's canonical constructor, and creates a structurally immutable object.

Because a record has no setters, a request also sending `role=ADMIN` has nowhere for property binding to assign `role` on this DTO. The constructor declares only `email` and `age`. However, that **does not mean** extra parameters are treated as errors by default; unbound values may simply be ignored by default.

A regular class can also use constructor binding:

```java
public final class SearchForm {
    private final String keyword;
    private final int page;

    public SearchForm(String keyword, int page) {
        this.keyword = keyword;
        this.page = page;
    }

    public String getKeyword() { return keyword; }
    public int getPage() { return page; }
}
```

This is an illustrative snippet. When relying on **constructor parameter names** of a regular class, ensure the compiler retains parameter-name metadata (e.g., `javac -parameters` or equivalent configuration). Records have explicit component names. When multiple constructors exist, constructor selection rules can vary; design a single unambiguous data constructor.

### Renaming Input Parameters with @BindParam

Request names do not have to match Java names. In Spring 6.1+, `@BindParam` supports mapping a request parameter name to a constructor parameter:

```java
public final class AddressForm {
    private final String postalCode;

    public AddressForm(@BindParam("postal-code") String postalCode) {
        this.postalCode = postalCode;
    }

    public String getPostalCode() { return postalCode; }
}
```

```http
GET /addresses?postal-code=700000
```

With `@ModelAttribute AddressForm`, Spring takes the `postal-code` parameter to populate `postalCode`. The annotation import is `org.springframework.web.bind.annotation.BindParam`. This is an illustration meant to live inside a Spring MVC application, not a standalone class with `main`. Do not confuse `@BindParam` used for `@ModelAttribute` constructors with Jackson's `@JsonProperty` used when deserializing JSON into objects.

Constructor binding can handle nested objects as well as `List`, `Map`, and arrays using structured names like `addresses[0].city`, provided the corresponding constructors/types are bindable and appropriate resource limits are applied. Do not allow clients to arbitrarily construct overly deep object graphs or unbounded collections.

## 4. Property Binding: Mutable Beans and Setters

Property binding typically uses a JavaBean class with a no-args constructor and getters/setters:

```java
public class ProfileForm {
    private String displayName;
    private String timeZone;

    public ProfileForm() {}

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getTimeZone() { return timeZone; }
    public void setTimeZone(String timeZone) {
        this.timeZone = timeZone;
    }
}
```

Given the form `displayName=Lan&timeZone=Asia%2FHo_Chi_Minh`, Spring instantiates `ProfileForm` and calls the corresponding setters. This approach is useful for mutable forms or when working with libraries requiring JavaBeans. It carries a risk: if a sensitive setter such as `setRole` is later added to the class, unrestricted binding could let clients modify unintended fields.

**Mass assignment / over-posting** happens when a client attempts to send sensitive property names that the server inadvertently binds, such as `role=ADMIN`, `approved=true`, or `ownerId=...`. Mitigation principles:

1. Use **dedicated input DTOs** per operation, containing only the fields the client is permitted to supply.
2. Prefer constructor binding or immutable DTOs when appropriate, avoiding unnecessary setters.
3. If property binding must be used, configure `WebDataBinder.setAllowedFields(...)` to whitelist expected property names.
4. Do not bind requests directly into JPA entities or domain objects that have sensitive business setters.
5. Have the server derive `id`, `role`, `ownerId`, `createdAt`, and `approved` from the current principal's permissions and business rules.

**Note:** the whitelist applies only to **property binding**; it does not alter which values are accepted by a declared constructor. Therefore, do not put dangerous parameters into a DTO's public constructor hoping `allowedFields` will block them.

## 5. Controlling WebDataBinder with @InitBinder

`WebDataBinder` is the concrete binder in Spring MVC. Use `@InitBinder` to customize how binding works for a model attribute or a controller:

```java
@InitBinder("profileForm")
void configureProfileBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "timeZone");
}
```

- `setAllowedFields` establishes an **allowlist** for property names; patterns are case-sensitive. Broad patterns like `address.*` can be used, but you must audit all nested properties being opened up.
- `setDisallowedFields` exists in relevant Spring versions, but a blocklist easily misses properties added later. Prefer an allowlist.
- `setDeclarativeBinding(true)` (Spring 6.1+) restricts property binding so it only occurs when `allowedFields` are configured, while constructor binding remains supported:

```java
@InitBinder("registrationForm")
void configureRegistrationBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

If **both** `setDeclarativeBinding(true)` and `setAllowedFields("displayName", "timeZone")` are used, the two whitelisted properties still undergo setter binding; other properties are not set via setters. For models that only need constructor binding, simply enable declarative binding without declaring allowed fields.

`@InitBinder("profileForm")` applies to the model attribute named `profileForm`; `@InitBinder` without a name can affect bindings within that controller. `@ControllerAdvice` can share policies across controllers, but verify the scope so you do not accidentally break other forms. When specifically needed, the binder can also register formatters, converters, or validators.

### @ModelAttribute(binding = false) Solves a Different Problem

`@ModelAttribute(binding = false)` is used when you need to retrieve an object from the model without performing request property binding on it, such as a domain object already looked up by the server. It is not a substitute for all constructor binding controls. A safer pattern for data-accepting APIs is using a separate request DTO and copying fields into the domain object under explicit control.

## 6. Complete Program: Comparing Both Binding Mechanisms

The example has two endpoints:
- `POST /api/registration`: immutable record DTO, constructor binding, and validation.
- `POST /api/profile`: JavaBean with setters, property binding via a whitelist. The illustrative class intentionally includes a `role` property to show how the whitelist blocks an unauthorized parameter. **In a real application, omit the `role` property from the input DTO altogether.**

Maven structure:

```text
binding-demo/
├── pom.xml
└── src/main/java/example/binding/
    ├── BindingDemoApplication.java
    └── BindingController.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>binding-demo</artifactId>
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

**`src/main/java/example/binding/BindingDemoApplication.java`**

```java
package example.binding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingDemoApplication.class, args);
    }
}
```

**`src/main/java/example/binding/BindingController.java`**

```java
package example.binding;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
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

import java.util.Map;

@RestController
@RequestMapping("/api")
public class BindingController {

    public record RegistrationForm(
            @NotBlank @Email String email,
            @Min(18) int age) {}

    public record RegistrationResponse(String email, int age) {}

    @InitBinder("registrationForm")
    void registrationBinder(WebDataBinder binder) {
        // Do not enable setter binding for RegistrationForm.
        binder.setDeclarativeBinding(true);
    }

    @PostMapping(path = "/registration",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> register(
            @Valid @ModelAttribute("registrationForm") RegistrationForm form,
            BindingResult errors) {
        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body(Map.of(
                "invalidFields",
                errors.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .toList()
            ));
        }
        return ResponseEntity.ok(
                new RegistrationResponse(form.email(), form.age()));
    }

    public static class ProfileForm {
        private String displayName;
        private String timeZone;
        private String role; // Kept to illustrate a field that must be blocked.

        public ProfileForm() {}

        public String getDisplayName() { return displayName; }
        public void setDisplayName(String value) {
            this.displayName = value;
        }

        public String getTimeZone() { return timeZone; }
        public void setTimeZone(String value) {
            this.timeZone = value;
        }

        public String getRole() { return role; }
        public void setRole(String value) {
            this.role = value;
        }
    }

    public record ProfileResponse(
            String displayName, String timeZone, String role) {}

    @InitBinder("profileForm")
    void profileBinder(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
        binder.setAllowedFields("displayName", "timeZone");
    }

    @PostMapping(path = "/profile",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public ProfileResponse update(
            @ModelAttribute("profileForm") ProfileForm form) {
        return new ProfileResponse(
                form.getDisplayName(), form.getTimeZone(), form.getRole());
    }
}
```

**Mechanism of each endpoint:**

- `/registration`: the record has a canonical constructor taking `email` and `age`; Spring converts strings to target types, creates the record, and runs Bean Validation because `@Valid` is present. `BindingResult` sits **immediately after** the validated parameter so the controller can read errors.
- `/profile`: the JavaBean is instantiated with its empty constructor; the binder only permits setters matching `displayName` and `timeZone`. The `role` parameter is blocked by the whitelist even though the demo class has a setter.
- This is an example contrasting mechanisms; it **does not save to a database**, has no authentication, and does not represent a real role-editing workflow.

Run from the `binding-demo` directory:

```bash
mvn spring-boot:run
```

Send a valid form (Bash, macOS/Linux/Git Bash):

```bash
curl -s -X POST 'http://localhost:8080/api/registration' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'email=lan@example.com' \
  --data-urlencode 'age=21'
```

HTTP status `200`; the JSON contains:

```json
{"email":"lan@example.com","age":21}
```

JSON field order should not be treated as an API contract. Try data violating constraints:

```bash
curl -i -X POST 'http://localhost:8080/api/registration' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'email=invalid' \
  --data-urlencode 'age=16'
```

Expected result is HTTP `400`, with a body containing the invalid field names (sorted in the controller):

```json
{"invalidFields":["age","email"]}
```

Test the blocked field:

```bash
curl -s -X POST 'http://localhost:8080/api/profile' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Lan' \
  --data-urlencode 'timeZone=Asia/Ho_Chi_Minh' \
  --data-urlencode 'role=ADMIN'
```

JSON output:

```json
{"displayName":"Lan","timeZone":"Asia/Ho_Chi_Minh","role":null}
```

Even though the request includes `role=ADMIN` and `ProfileForm` has a setter, `setAllowedFields` accepts only the other two fields, so `role` is not assigned. The response only helps observe the mechanism; in a real application **you should not return internal roles when unnecessary**. To detect blocked fields during form handling, declare `BindingResult` immediately after `@ModelAttribute` and check `getSuppressedFields()`; decide on a policy to return an error or log the event based on API security rather than assuming silent ignoring is sufficient.

> **Runtime verification:** the bodies above follow the controller's logic for the stated requests; HTTP headers depend on the environment. The code requires Maven and JDK 17+, with dependencies downloaded successfully. If port `8080` is already in use, configure an appropriate `server.port` before sending requests.

## 7. When the Input Is JSON @RequestBody

Sending JSON:

```http
POST /api/registration-json HTTP/1.1
Content-Type: application/json

{"email":"lan@example.com","age":21}
```

The controller typically declares:

```java
@PostMapping(path = "/registration-json",
             consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<?> createJson(
        @Valid @RequestBody RegistrationForm form) {
    // ...
}
```

**The snippet above is illustrative** and can be added to `BindingController` with the `@RequestBody` import; it is not included in the complete runnable file in Section 6. Here Spring MVC selects an `HttpMessageConverter` to read JSON, and Jackson (if configured) constructs the Java object. Validation can still run after reading the body, but this is **not** the `@ModelAttribute` process that invokes `WebDataBinder` to assign request parameters via property binding. Therefore, `binder.setAllowedFields(...)` in `@InitBinder` is not a mechanism for protecting JSON from mass assignment.

For JSON, use request DTOs with only the allowed fields, map explicitly to the domain model, and permit only the necessary JSON properties. If strict rules on unknown JSON fields are required, configure Jackson's unknown-property handling accordingly; whether unknown fields are accepted or rejected by default depends on ObjectMapper and environment configuration. `@JsonProperty`/`@JsonCreator` serve Jackson; `@BindParam` serves Spring MVC constructor binding for `@ModelAttribute`.

| Aspect | `@ModelAttribute` with form/query | `@RequestBody` with JSON |
| --- | --- | --- |
| Typical data source | Query/form parameters; can also read URI variables/headers per lookup rules | HTTP body by `Content-Type` |
| Main component | `WebDataBinder`, conversion service | `HttpMessageConverter`, Jackson for JSON |
| Object creation | Constructor binding or bean/property binding | JSON deserialization per Jackson configuration |
| Property whitelist via `setAllowedFields` | Effective for **property binding** | Not a JSON whitelisting control |
| Bean Validation `@Valid` | Yes, often paired with `BindingResult` | Yes, validation errors handled via request body flow |

## 8. Designing Safe, Maintainable Input DTOs

A profile update endpoint should clearly separate **client input**, **domain object**, and **response DTO**:

```text
HTTP request
     |
CreateProfileRequest / UpdateProfileRequest
     |  validate + authorize + check business rules
     v
Application service
     |  map only allowed fields
     v
Domain entity (id, role, ownerId managed by server)
     |
     v
ProfileResponse (only displayable data)
```

A well-designed input DTO typically has these characteristics:

1. **Action-oriented, not database-table-oriented.** E.g., `CreateOrderRequest`, `UpdateProfileRequest`; the two operations have different sets of allowed fields.
2. **Constrain data directly in the type.** Use records/final fields for immutable DTOs where suitable, with constraints like `@NotBlank`, `@Email`, `@Size`, `@Min`; do not treat annotations as the entirety of business logic.
3. **Exclude server-owned fields.** `id`, `createdAt`, `approved`, `role`, `tenantId`, and `ownerId` should usually be resolved from the database or security context after authentication/authorization.
4. **Map only valid fields.** Do not copy all request properties into an entity via reflection or unchecked `BeanUtils`. Assign manually or use a mapper with explicit mappings.
5. **Separate creation and update types.** For partial updates, you must distinguish **omitted field**, **explicit null**, and **new value**; a record with a primitive `int` or a simple nullable reference may lose this distinction. If patch semantics matter, design an appropriate command/patch representation.
6. **Treat nested objects/lists as external data.** Bound the element count and depth, and verify that every referenced ID is within authorized scope.
7. **Standardize errors.** Place `BindingResult` right after the `@ModelAttribute` parameter when handling field errors directly in the controller; otherwise let Spring handle errors via an exception handler. Do not leak sensitive values into error responses or logs.

Explicit mapping example (**service logic illustration**, not a standalone runnable class):

```java
public void changeProfile(UpdateProfileRequest input,
                          Account account) {
    account.changeDisplayName(input.displayName());
    account.changeTimeZone(input.timeZone());
    // account.role and account.ownerId do not come from input.
}
```

The `account` object must be loaded and authorized in the service/security layer. Binder whitelists and narrow DTOs reduce the attack surface, but they cannot replace record ownership checks.

## 9. Common Mistakes and Misconceptions

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Form sends the right names, but fields stay `null` | Missing/wrong getter/setter, mismatched request name, blocked by `allowedFields` | Verify JavaBean conventions, parameter names, and binder |
| `age=abc` causes a binding error | Cannot convert `String` to `int` | Check `BindingResult` and return structured messages |
| `age=16` binds, but validation fails | Type conversion succeeds, `@Min(18)` fails | Distinguish validation from conversion |
| DTO with sensitive setter gets modified by client | Property binding is too permissive | Use dedicated DTOs and `setAllowedFields`/`setDeclarativeBinding` |
| Enabling `setDeclarativeBinding(true)` stops a mutable form from receiving values | Property binding requires explicit `allowedFields` | Add an exact whitelist or switch to a constructor-based DTO |
| `BindingResult` placed in the wrong position | Spring requires it immediately after the matching argument | Move `BindingResult` right after `@Valid @ModelAttribute` |
| Confusing `@BindParam` with `@JsonProperty` | Two different pipelines | Distinguish model attribute binder from Jackson |
| Assuming removing `role` from JSON equals authorization | Authorization is a separate check | Verify principal, resource ownership, and policies in the service |
| Reusing one request DTO for create/update/patch | Field and null semantics differ | Split contracts or build a representation expressing intent clearly |

Subtle details to remember:

- `@ModelAttribute` can source values from request parameters, URI variables, and headers; Spring prioritizes request parameters on name collisions. Do not rely on headers to supply sensitive fields just because the binder can read them.
- `setAllowedFields` restricts setter/property binding; it **does not remove binding for parameters declared in a constructor**.
- `BindingResult` holds both binding/conversion errors and validation errors; if a controller declares it, it must inspect and handle it rather than proceeding to the service when errors exist.
- Spring MVC typically returns `400 Bad Request` for unhandled binding/validation failures, though the JSON error structure depends on the application, version, and exception handlers.
- Risks around request size, large lists, nested binding, and sensitive data must be addressed with appropriate limits at both HTTP and business layers.

## 10. Self-Check Exercises

1. Why should a request DTO's constructor accept only fields the client is genuinely allowed to control?
2. How does `setDeclarativeBinding(true)` affect constructor binding and property binding?
3. If a JavaBean class has setters `setName` and `setRole`, and allowed fields include only `name`, what happens to a request with `role=ADMIN`?
4. Why doesn't `@Valid` replace `setAllowedFields`? And why doesn't `setAllowedFields` replace authorization?
5. Which mechanism should you choose for an HTML form containing `email` and `age`? Which mechanism for a JSON request with the same two fields?
6. When designing PATCH, why is `int age` in a record insufficient to distinguish an omitted field from sending `0`?

**Answer guidance:** (1) Constructor parameters form the explicitly declared input set; never let server-owned fields enter. (2) Constructor binding still works; setter binding works only with a whitelist. (3) `role` is excluded from property binding. (4) Validation checks values, whitelisting controls which fields are assigned, and authorization checks permissions. (5) Form/query: `@ModelAttribute`; JSON: `@RequestBody` via converter. (6) Primitives have defaults, so you need a model representing presence state if supporting partial updates.

## 11. References

- [Spring Framework — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — Data Binding (Web MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring Framework — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework — Data Binding (Core)](https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html)
- [Spring Framework 6.1 — DataBinder API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.1 — @BindParam API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/bind/annotation/BindParam.html)

Examples are scoped to Spring MVC, input binding, and DTO design; they illustrate safe request handling within the lesson's scope without persistence or login mechanisms.