# Deliberately Combining Constructor Binding and Property Binding in Spring Framework

> **Topic:** Spring Framework – Validation & Data Binding  
> **Knowledge group:** Constructor Binding  
> **Context:** Spring Framework 6.1+/6.2, Spring MVC, Java 17 or newer. This article explains how Spring can instantiate an object via a constructor and then assign permitted properties, how to configure the boundary between the two phases, and how to prevent unintended data overwrites.

## 1. The Problem: An Object with an Immutable Part and an Editable Part

Suppose a profile creation form consists of:

- `email`: must be provided at creation time; must not be arbitrarily changed via a setter.
- `age`: accepted at creation time, converted from request string to integer, and range-checked.
- `displayName`: a property allowed to be supplied or updated via a setter.
- `role`: internal information; clients must not escalate their own privileges.

There are two distinct binding mechanisms:

1. **Constructor binding**: Spring looks up values by constructor parameter names, converts types, and uses those arguments to **create the instance**.
2. **Property binding**: Spring looks up values by JavaBeans property names and uses configured setters/field access to **assign onto an existing instance**.

Spring MVC, when handling `@ModelAttribute`, can use both. Using them together is only safe when you have clearly decided **which data is accepted in the constructor**, **which data may be written afterward**, and **what happens if a client sends unexpected names**.

**Design goal:** constructor parameters define the data required to construct a valid object; property binding only supplements properties permitted to change. Explicitly control both input name sets, especially when requests come from external users.

## 2. How Do the Two Mechanisms Differ?

| Criterion | Constructor binding | Property binding |
| --- | --- | --- |
| Purpose | Create an object from input parameters | Update properties of an existing object |
| Data target | Parameters of the selected constructor | Properties with setters or appropriate field access |
| Input keys | Constructor parameter names, optionally mapped via `@BindParam` | Property names/paths such as `displayName` or `address.city` |
| Suitable object types | Records, immutable DTOs, classes with data constructors | Mutable JavaBeans, objects with setters |
| Mutability after creation | The construct step itself requires no setters | Can mutate state after constructor execution |
| Field restriction | Constructor shape defines the list of parameters accepted | Needs `allowedFields`/DTO restrictions or disabling this phase |
| Errors | Conversion/constructor instantiation, surfaced via binding result or exception depending on scenario | Conversion, field path, setter errors collected or reported by binder |
| Risks | Constructor taking too many sensitive parameters; wrong constructor chosen; missing name metadata | Mass assignment, field overwrites, unintended nested path updates |

**Constructor binding does not mean Bean Validation**: a constructor can successfully create an object with `age=0`; a `@Min(18)` rule must still be triggered and checked after binding. Similarly, property binding can convert a string into a type-valid number that still violates business policy.

## 3. Typical Sequence of `@ModelAttribute` in Spring MVC

```text
HTTP request: email=linh@example.com&age=21&displayName=Linh&role=ADMIN
            |
            v
Does Spring find an existing model attribute?
      | Yes                           | Not yet
      v                               v
Use instance from model/session   Create instance via default constructor
or matching source                or primary/data constructor
      |                               | (constructor binding)
      +---------------+---------------+
                      |
                      v
        WebDataBinder and @InitBinder config
                      |
                      v
    Property binding onto the existing target
      - May apply by default
      - With declarativeBinding + allowedFields:
        only permitted setter fields
                      |
                      v
        Validation when triggered
                      |
                      v
     BindingResult / Controller / Service
```

This diagram is a mental model for the `@ModelAttribute` path, not a claim that every request invokes a constructor: Spring MVC can retrieve an existing attribute from the model, session, or an appropriate source/`Converter`. In that case, no new constructor binding runs for the already-prepared instance.

For a newly created attribute via constructor, **constructor binding happens before assigning properties onto the created object**. Spring MVC by default can proceed with property binding after construction, so if the same data has both a constructor parameter and a setter, watch out for duplicate assignment or overwrites.

Data source note: `@ModelAttribute` in Spring MVC can bind request parameters (including query and form data) as well as additional sources such as URI variables/headers per framework rules. **`@RequestBody` JSON goes through an HTTP message converter/Jackson**, which has its own deserialization mechanism; do not treat `WebDataBinder.setDeclarativeBinding` as a default guard for JSON fields.

## 4. Conditions for Spring to Select the Right Constructor

With a class that has only one data constructor:

```java
public final class RegistrationForm {
    private final String email;
    private final int age;

    public RegistrationForm(String email, int age) {
        this.email = email;
        this.age = age;
    }

    public String getEmail() { return email; }
    public int getAge() { return age; }
}
```

When receiving a request with `email` and `age` parameters, Spring MVC can use constructor parameter names to look up values, convert `"21"` to `int 21`, and create the instance. To read parameter names at runtime, compile Java with the `-parameters` option (Spring Boot Maven parent usually configures this; it can be set explicitly in Maven compiler settings).

Things to verify:

- **Selected constructor:** with a single data constructor, mapping is straightforward. If the class has multiple constructors, check your Spring version's constructor selection rules, especially when a no-argument constructor exists; never assume Spring always picks the constructor with the most parameters.
- **Parameter names must match the source:** `email` and `age` are the names Spring looks for by default. If request names must differ from Java variable names, use `@BindParam`.
- **Type conversion:** a string that cannot convert to `int` raises an error. Do not use Java's default primitive values to mask conversion errors.
- **Nested constructor arguments:** Spring 6.1+ can construct nested objects by property path from provided data, and supports collection/map/indexed inputs under specific rules.
- **Records/immutable DTOs:** work very well with constructor binding; no setters needed. A `record` has a canonical constructor; you cannot expect property binding to mutate final components afterward.

If a constructor has a client-controlled `role` parameter, **enabling `setAllowedFields` will not block that constructor parameter**: that allowlist protects *property binding*, whereas constructor binding accepts parameters per the constructor signature. Design input constructors without privileged fields instead of expecting a setter allowlist to guard constructors.

### Name Mapping with `@BindParam`

When the request name is `first-name` while the Java parameter name is `firstName`:

```java
import org.springframework.web.bind.annotation.BindParam;

public PersonForm(@BindParam("first-name") String firstName) {
    this.firstName = firstName;
}
```

This is **an illustrative constructor inside `PersonForm`**, not a standalone Java source file. `@BindParam` can map names in MVC/WebFlux constructor binding, and can also be placed on the corresponding field where Spring supports it. It does not generate setters or allow property binding onto names outside the allowlist.

## 5. Property Binding Is the Next Step: Decide Whether to Allow It

Distinguish three configurations:

| Configuration | Intended behavior |
| --- | --- |
| Default, unrestricted | Constructor binding can create the object; afterward property binding can assign any matching writable property. On objects with internal fields, this is a risk. |
| `binder.setDeclarativeBinding(true)` **without** setting `allowedFields` | Uses only constructor binding when creating the object; property binding is disabled in declarative mode. |
| `binder.setDeclarativeBinding(true)` with `binder.setAllowedFields("displayName")` | Constructor binding still runs; property binding applies only to the permitted property patterns. |

`setDeclarativeBinding(true)` is supported since Spring Framework 6.1. This flag requests declarative binding: constructor arguments are still bound, while setters/properties are bound only if `allowedFields` is configured.

In Spring MVC:

```java
@InitBinder("profileForm")
void configureProfileBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields("displayName");
}
```

The snippet above is a method in a controller or advice, needing `org.springframework.web.bind.annotation.InitBinder` and `org.springframework.web.bind.WebDataBinder` imports. `"profileForm"` must match the corresponding model attribute name. The constructor can accept `email`/`age`, while the setter phase accepts only `displayName`.

Keep in mind:

- `setAllowedFields(...)` applies to **property binding**, not the mechanism receiving constructor parameters.
- Patterns support wildcards; prefer explicit names whenever possible. Overly broad patterns can unintentionally expose newly added fields later.
- `setDisallowedFields(...)` is a denylist approach that easily misses new fields; an allowlist is usually easier to control.
- When the binder excludes fields from the property phase, `BindingResult.getSuppressedFields()` can show which names were blocked. **Do not assume every suppressed field is an attack**: names already legitimately consumed in the constructor phase can also appear in the request set filtered out by the property phase.
- Enabling declarative binding **does not mean** all DTO fields are automatically verified for access rights or business rules; you still need validation and authorization checks at the proper layer.

## 6. Designing a Hybrid Form: Immutable Core + Mutable Part

A fitting model when genuinely needing to combine both steps:

```java
package demo.hybrid;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public final class ProfileForm {

    @NotBlank
    @Email
    private final String email;

    @Min(18)
    private final int age;

    @NotBlank
    private String displayName;

    // Setter included only to demonstrate mass assignment risk.
    // In production design, remove role from input DTO.
    private String role = "USER";

    public ProfileForm(String email, int age) {
        this.email = email;
        this.age = age;
    }

    public String getEmail() {
        return email;
    }

    public int getAge() {
        return age;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getRole() {
        return role;
    }

    public void setRole(String role) {
        this.role = role;
    }
}
```

The intents expressed in this class:

1. `email` and `age` are creation data, **have no setters**, and are declared `final`.
2. `displayName` has a setter to receive property binding after the instance is created.
3. `role` has a setter but is **not in allowedFields**, showing that the binder must be configured deliberately if the class has other properties.
4. `@NotBlank`, `@Email`, and `@Min` are data validation constraints; they **do not run automatically just because constructors or setters are called**. In controllers, use `@Valid` to trigger Bean Validation.

This class illustrates binding boundaries. In real production code, design input DTOs **without a `role` field** from the start, deriving roles from permissions and policies in the application/domain layer.

## 7. Runnable Java 17 Spring Boot 3.5.7 Example

Below is a small web project demonstrating **one request using both constructor and property binding via allowedFields**. Spring Boot 3.5.7 used in this example is published on Maven Central; it is compatible with Java 17 and the Spring Framework 6.2.x API set.

Structure:

```text
hybrid-binding-demo/
  pom.xml
  src/main/java/demo/hybrid/HybridBindingApplication.java
  src/main/java/demo/hybrid/ProfileForm.java
  src/main/java/demo/hybrid/ProfileController.java
  src/test/java/demo/hybrid/ProfileControllerTest.java
```

### 7.1. `pom.xml`

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
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>hybrid-binding-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.parameters>true</maven.compiler.parameters>
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

### 7.2. `HybridBindingApplication.java`

```java
package demo.hybrid;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HybridBindingApplication {

    public static void main(String[] args) {
        SpringApplication.run(HybridBindingApplication.class, args);
    }
}
```

### 7.3. `ProfileForm.java`

Use the exact `ProfileForm` contents from section 6, saved at the file path above. `-parameters` in the Maven configuration enables Spring to read constructor parameter names `email`/`age` when binding.

### 7.4. `ProfileController.java`

```java
package demo.hybrid;

import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.validation.Valid;
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
@RequestMapping("/profiles")
public class ProfileController {

    @InitBinder("profileForm")
    void initBinder(WebDataBinder binder) {
        // Constructor arguments are still used to create ProfileForm.
        binder.setDeclarativeBinding(true);

        // Setter phase is only allowed to assign displayName.
        binder.setAllowedFields("displayName");
    }

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Map<String, Object>> create(
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(Map.<String, Object>of(
                            "error", "INVALID_FORM"));
        }

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("email", form.getEmail());
        response.put("age", form.getAge());
        response.put("displayName", form.getDisplayName());
        response.put("role", form.getRole());
        return ResponseEntity.ok(response);
    }
}
```

Why is the controller written this way?

- `@ModelAttribute("profileForm")` declares the attribute name handled by Spring MVC; `@InitBinder("profileForm")` configures the binder specifically for that attribute.
- `ProfileForm` has one public two-parameter constructor and no empty constructor; when creating a new instance, Spring uses `email` and `age` data for constructor binding.
- After the instance exists, `setAllowedFields("displayName")` allows the setter phase to accept only `displayName`. A request trying to send `role=ADMIN` is **not assigned** via property binding.
- `@Valid` triggers validation; `BindingResult` must come **immediately after the model attribute parameter** to handle errors for that object.
- `BindingResult.hasErrors()` checks binding/validation errors; it does not replace checking authorization to create a profile in a real service.
- The endpoint only returns illustrative data without accessing a DB. In a real application, the controller calls a service to check business rules and persist a safe domain entity.

### 7.5. Sending Requests and Observing Results

Start from the `hybrid-binding-demo` directory:

```bash
mvn spring-boot:run
```

On Windows, if Maven Wrapper is present, use `mvnw.cmd spring-boot:run`; if using the command above, Maven must be on PATH.

Send a form-encoded request:

```bash
curl -X POST "http://localhost:8080/profiles" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "email=linh@example.com" \
  --data-urlencode "age=21" \
  --data-urlencode "displayName=Linh"
```

Successful HTTP result by **values** (JSON key order may vary by serializer):

```json
{
  "email": "linh@example.com",
  "age": 21,
  "displayName": "Linh",
  "role": "USER"
}
```

Send an additional field not allowed via setter:

```bash
curl -X POST "http://localhost:8080/profiles" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "email=linh@example.com" \
  --data-urlencode "age=21" \
  --data-urlencode "displayName=Linh" \
  --data-urlencode "role=ADMIN"
```

With the configuration above, the object's `role` remains `"USER"`. This only proves the field allowlist mechanism; real APIs should also decide error policies for extra keys and omit roles from DTOs when unnecessary.

If `age=abc` is sent, the value cannot convert to `int`; the request should be treated as a binding error rather than silently defaulting to `0` or continuing profile creation. If `displayName=` is sent, `@NotBlank` reports an error when validation runs.

The demonstrated path is **`@ModelAttribute` form data**. If switching the endpoint to `@RequestBody` JSON, the constructor/setter notes here must be revisited per Jackson rules; specifically, `@InitBinder.setAllowedFields` is not a Jackson JSON field blocking policy.

## 8. Testing the Combined Mechanism with `MockMvc`

Save `src/test/java/demo/hybrid/ProfileControllerTest.java`:

```java
package demo.hybrid;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProfileController.class)
class ProfileControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void combinesConstructorAndPropertyBinding() throws Exception {
        mvc.perform(post("/profiles")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("email", "linh@example.com")
                    .param("age", "21")
                    .param("displayName", "Linh"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.email")
                        .value("linh@example.com"))
                .andExpect(jsonPath("$.age").value(21))
                .andExpect(jsonPath("$.displayName").value("Linh"))
                .andExpect(jsonPath("$.role").value("USER"));
    }

    @Test
    void cannotChangeRoleViaPropertyBinding() throws Exception {
        mvc.perform(post("/profiles")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("email", "linh@example.com")
                    .param("age", "21")
                    .param("displayName", "Linh")
                    .param("role", "ADMIN"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.role").value("USER"));
    }

    @Test
    void rejectsBlankDisplayName() throws Exception {
        mvc.perform(post("/profiles")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("email", "linh@example.com")
                    .param("age", "21")
                    .param("displayName", ""))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error")
                        .value("INVALID_FORM"));
    }
}
```

Run:

```bash
mvn test
```

The three tests verify different things:

1. `email` and `age` go through constructor binding; `displayName` goes through property binding.
2. `role` is not in allowedFields, so it cannot be modified in the setter phase even though a setter exists.
3. A blank `displayName` value is assigned and then rejected by Bean Validation; this is post-binding validation, not a condition resolved by the constructor itself.

**Testing note:** the example provides a complete Spring Boot project structure, yet still depends on runtime and dependencies fetched by Maven. The article describes expected outcomes per the API; in real projects run `mvn test` against your deployed version and inspect actual reports, especially when custom converters, `@ControllerAdvice`, or global binder configs exist.

## 9. Ordering and Avoiding Conflicts Between Constructor Fields and Setter Fields

A field present in both the constructor and a setter can cause both phases to process the data:

```java
public class AmbiguousForm {
    private String name;

    public AmbiguousForm(String name) {
        this.name = name;
    }

    public String getName() { return name; }

    public void setName(String name) {
        // May differ from normalization logic in constructor.
        this.name = name;
    }
}
```

If property binding continues for `name`, the setter may run after the constructor has already processed `name`. Even with identical input values, running logic twice can affect normalization, side effects, or invariant checks.

Cleaner design:

- **Identity/immutable creation data:** use the constructor, `final` fields, no setters; e.g., `email` at DTO creation time.
- **Data allowed to be added/edited:** use dedicated setters with permitted property names; e.g., `displayName`.
- **Internal properties:** do not put them in client-controlled constructors; do not permit setter binding; ideally omit them from input DTOs.
- **Single source of truth for validation:** validate on the final state; if rules exist inside constructors, keep them aligned with Bean Validation/business policies without losing clear error reporting.

Do not write constructors with side effects like database writes, sending emails, or publishing messages. Binding can fail after the constructor has executed, causing side effects even though the request is rejected. Keep constructors pure (initializing and guarding internal invariants), while business actions execute in services after validation.

## 10. Scenarios Without Constructor Binding Because the Object Already Exists

Spring MVC can obtain a model attribute from:

- A model prepared by an `@ModelAttribute` method.
- `@SessionAttributes` and the associated session.
- A matching converter for a parameter/path variable.
- Another attribute-creation mechanism selected by the framework.

When an instance already exists, Spring may **skip creating a new one via the data constructor**. Property binding on that existing instance (if permitted) can mutate existing data.

For example, a controller loading a domain entity by ID and directly binding the whole request onto it is especially risky: an unprotected property setter can alter values unexpectedly. Separate **input form DTOs** from **domain entities**, validate the DTO, and then call a controlled business method to update the entity.

If you only want to pass an attribute into a handler **without binding request data onto it**, use `@ModelAttribute(binding = false)` per the MVC contract. Depending on the use case, this is far safer than opening property binding on an entity loaded from the DB.

## 11. Distinguishing `@ModelAttribute` from `@RequestBody`

| Question | `@ModelAttribute` | `@RequestBody` |
| --- | --- | --- |
| Typical input | Query/form parameters, URI variables, headers per MVC rules | HTTP body content such as JSON |
| Primary mechanism | WebDataBinder, constructor/property binding | HttpMessageConverter, usually Jackson for JSON |
| Use `@InitBinder.setAllowedFields` for setters? | Meaningful for property binding via WebDataBinder | Not the mechanism restricting fields when Jackson deserializes JSON |
| Immutable objects | Data constructors/records fit well | Jackson can use canonical constructors/creators per its own configuration |
| Validation | `@Valid`/`@Validated` when triggered | `@Valid`/`@Validated` when triggered |
| Security concerns | Binds unintended fields if DTO/setters are overly open | JSON can map into unintended fields/setters/creators per Jackson config |

Both paths can accept Java DTOs, yet they do not use the exact same binding pipeline. If an application has both HTML form and JSON endpoints, test each endpoint separately; never assume one `@InitBinder` protects all data paths.

## 12. Interacting with `DataBinder` Manually

Outside Spring MVC, you can use `DataBinder` programmatically to see the boundary between the two phases. With Spring Framework 6.1+:

```java
import java.util.Map;
import java.util.Set;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.core.ResolvableType;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

// ProfileForm has a data constructor and setter as in the example above.
Map<String, String> input = Map.of(
        "email", "linh@example.com",
        "age", "21",
        "displayName", "Linh",
        "role", "ADMIN");

DataBinder binder = new DataBinder(null, "profileForm");
binder.setTargetType(ResolvableType.forClass(ProfileForm.class));
binder.setDeclarativeBinding(true);
binder.setAllowedFields("displayName");

DataBinder.ValueResolver resolver = new DataBinder.ValueResolver() {
    @Override
    public Object resolveValue(String name, Class<?> type) {
        return input.get(name);
    }

    @Override
    public Set<String> getNames() {
        return input.keySet();
    }
};

// Phase 1: create object via constructor.
binder.construct(resolver);

// Phase 2: bind only allowed properties onto the existing object.
if (binder.getTarget() != null) {
    binder.bind(new MutablePropertyValues(input));
}

BindingResult result = binder.getBindingResult();
// Check result.hasErrors() and use target only when valid.
```

This is an **API illustration snippet** meant for a class/method that already has `ProfileForm`, not a standalone Java file with `main`. When deploying, compile with `-parameters` or provide a suitable parameter name mapping mechanism.

Meaning of the steps:

1. `new DataBinder(null, "profileForm")` starts without a target.
2. `setTargetType(ResolvableType.forClass(ProfileForm.class))` specifies the type to construct.
3. `construct(ValueResolver)` resolves values by constructor parameters and builds the object if successful.
4. `bind(MutablePropertyValues)` runs the property phase per `allowedFields`.
5. `BindingResult` captures errors from applicable steps; `getTarget()` may still lack an instance if construction failed.

**Important:** calling `construct` and `bind` does not automatically run Bean Validation if you use `DataBinder` manually without configuring/invoking a validator. In Spring MVC, `@Valid` on `@ModelAttribute` participates in framework-managed validation lifecycles.

## 13. Error Handling and Validation Across Both Phases

At least three error sources must be distinguished:

1. **Constructor/type conversion:** parameter `age=abc` fails conversion to `int`, or the constructor rejects data. The outcome depends on error type, configuration, and framework version; do not assume the object was constructed successfully.
2. **Property binding:** setter `displayName` may receive a wrong-typed value, or a nested path may be invalid; the binder records field errors or raises exceptions per contract.
3. **Bean Validation and business rules:** `@NotBlank`/`@Min` are checked on the object via `@Valid`/validators; policies like "allowed to create profile" belong in the service/domain layer.

In MVC:

```java
@PostMapping("/sample")
public String example(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "profile-form";
    }
    return "profile-success";
}
```

This is a snippet in an MVC controller with `profile-form`/`profile-success` views; it is not a method to drop verbatim into the REST `ProfileController` in section 7.

`BindingResult` should appear **immediately after** the corresponding model attribute. Never insert an unrelated parameter in between and expect `BindingResult` to still capture that attribute's errors.

`BindingResult.getSuppressedFields()` helps when observing fields blocked by the property filter. However, when constructor arguments remain in the request set passed to the property phase, they can also be suppressed by the setter allowlist. Therefore, to **reject all parameters outside the request contract**, validate allowed keys at the API boundary with awareness of both **constructor keys** and **setter keys**; you cannot simply treat every suppressed key as malicious.

Without a `BindingResult` argument, Spring MVC normally throws an exception for binding/validation errors (e.g., `MethodArgumentNotValidException`); some method-validation configurations raise different exception types. Design `@ControllerAdvice` and test HTTP contracts against your project's Spring version.

## 14. Missing Values, Null, Defaults, and Conversion

| Input | Point to determine |
| --- | --- |
| `email` omitted | Constructor may receive `null` for reference parameter; `@NotBlank` validation rejects it if triggered and the object is constructed. |
| Primitive `age` omitted | Primitive defaults and constraints can affect the result; never treat `0` as proof the client sent `0`. |
| `age=xyz` sent | Conversion error; do not silently fall back to an arbitrary number. |
| `displayName` omitted | Setter phase assigns nothing; field retains its initial value (if any); `@NotBlank` rejects if still null/blank. |
| `displayName=` sent | An empty string may be assigned, then rejected by `@NotBlank`. |
| `role=ADMIN` sent | With allowedFields containing only `displayName`, setter `role` receives no value. |
| JSON `{"role":"ADMIN"}` sent to `@RequestBody` | Must be controlled via DTO/Jackson and separate API policy; `WebDataBinder` does not guard this JSON path. |

Do not "fix" bad values into defaults merely because binding seems convenient. If dynamic defaults based on user, tenant, or time are needed, compute them in the application service and re-verify invariants after resolving final values.

## 15. With Nested Objects and Collections, Pick One Phase to Own Each Path

Spring constructor binding can construct nested objects using nested parameter names; property binding can likewise write paths like `address.city` or `items[0].quantity` when targets and converters fit.

If you both construct `address` from `address.city` and allow the setter phase to write `address.city`, that data may be processed twice. For complex object graphs:

- Decide which nested objects are **immutable and belong to the constructor phase**.
- Open setter paths only for supplemental fields that genuinely need modification.
- Control `allowedFields` with specific patterns, avoiding overly broad wildcards like `"*"`.
- When using collections/indexed fields, limit size, index, and auto-grow appropriately to prevent unintended large object graphs.
- Nested validation usually requires `@Valid` to cascade into child objects and constraints on child fields.
- Do not treat a nested path open for binding as permission for users to update the entire child object.

Separating constructor keys from property keys in your design avoids ambiguity when multiple components touch the same path.

## 16. Three DTO Styles and Choosing Appropriately

| Style | Example | Recommendation |
| --- | --- | --- |
| **Constructor-only** | `record SearchRequest(String query, int limit)` | Simple, clear which fields are created; well suited for immutable input APIs. Use declarative binding if preventing setter binding in MVC contexts with other objects. |
| **Property-only** | JavaBean with empty constructor, setters for editable fields | Fits legacy forms or mutable binding tools; use dedicated DTOs and allowedFields when accepting untrusted data. |
| **Controlled hybrid** | `ProfileForm(String email, int age)` + `setDisplayName` | Use only when you genuinely have both creation parameters and supplemental properties; enable declarativeBinding and explicit setter allowlists. |

Do not pick hybrid just because the framework supports it. If there is no reason for a setter phase, an immutable DTO with a constructor/record is usually simpler. If a fully mutable form is needed, a dedicated mutable input DTO can be easier to understand. Decide based on data semantics and object lifecycle, not annotation count.

## 17. Common Design Mistakes

**Mistake 1: Assuming `@ModelAttribute` always calls only setters.** With a data constructor or record, Spring can use constructor binding to instantiate the object, followed by property binding if permitted.

**Mistake 2: Having both a no-arg constructor and a data constructor and assuming Spring picks the data constructor.** Constructor selection rules depend on class structure; a default constructor may take precedence when multiple constructors exist. Design classes clearly and test them.

**Mistake 3: Putting privileged fields in the constructor and trusting `allowedFields` to block them.** `allowedFields` applies to property binding; it does not replace safe constructor input design.

**Mistake 4: Enabling `setDeclarativeBinding(true)` and forgetting to declare `allowedFields` for needed setter fields.** The property phase will not bind those fields automatically; `displayName` may stay null and fail validation.

**Mistake 5: Using setters for the exact same values initialized by the constructor.** This can cause duplicate assignment, overwrites, double normalization, or side effects. Clearly divide field ownership between the two phases.

**Mistake 6: Using a JPA entity as an input model.** Entities can expose many setters outside the request contract or carry DB-loaded state. Accept a DTO and update entities through services.

**Mistake 7: Assuming `@RequestBody` JSON uses `@InitBinder`'s allowedFields policy.** JSON deserialization has a separate pipeline.

**Mistake 8: Treating conversion as validation.** Converting `"0"` to `int 0` cleanly does not mean the data satisfies `@Min` or business rules.

**Mistake 9: Omitting `BindingResult` or placing it in the wrong position.** You may fail to receive binding/validation errors in the controller as expected.

**Mistake 10: Treating every suppressed field as an attack.** In hybrid binding, valid constructor parameter names can still be listed during the property phase; evaluate the full request contract.

**Mistake 11: Putting side effects in constructors/setters.** A rejected request may already have executed constructors/setters. Side effects and transactional domain changes belong in services after data is verified.

**Mistake 12: Not testing ordering and boundaries between the two phases separately.** A test suite with only valid requests can miss privileged fields, name collisions, conversion errors, and nested paths.

## 18. Recommended Test Matrix

| Case | Expectation |
| --- | --- |
| Valid `email`/`age`/`displayName` submitted | Constructs form via constructor, supplements displayName via setter, validation passes. |
| Only constructor fields sent, missing displayName | Rejected by `@NotBlank` per contract. |
| `age=abc` | Conversion error in constructor binding, never silently defaults. |
| `age=17` | May construct, yet rejected by `@Min(18)`. |
| `role=ADMIN` sent | Does not change role via setter when allowlist contains only displayName. |
| Declarative binding enabled with no allowedFields | Constructor binding only; setter fields do not receive data automatically. |
| Input DTO with multiple constructors | Verifies exact constructor selected. |
| `@BindParam` used for hyphenated names | External name maps properly to constructor argument. |
| Object already present in model | Does not assume constructor binding runs again; tests property updates. |
| JSON `@RequestBody` with out-of-contract field | Rejected/restricted via proper JSON DTO mechanisms; does not rely on @InitBinder. |
| Nested field with overlapping name across phases | Verifies no duplicate assignment or unintended override. |
| Inspecting suppressed fields | Does not equate valid constructor keys with malicious fields. |

In integration tests, use `MockMvc` for binder behavior and HTTP statuses, unit tests for DTO construction/normalization rules, and separate service/domain tests for permissions and business logic. In real applications, security testing should cover forms, JSON, and other adapters if they share DTOs.

## 19. Deliberate Design Process for a New Form

1. **List all fields in the input contract** and separate client-supplied sources from data derived from the login session or server.
2. **Choose fields needed to instantiate the object**: place them in a clear data constructor or record, excluding client-controlled privileged fields.
3. **Decide if property binding is truly needed**: if not, use an immutable input and disable the setter phase via declarative binding.
4. If a setter phase is present, **list permitted property names** via `setAllowedFields(...)` and enable `setDeclarativeBinding(true)`.
5. **Avoid name overlap** between constructor arguments and writable setter paths; when unavoidable, specifically test ordering and final results.
6. **Lock down types, names, and conversion**: ensure runtime has constructor parameter name metadata; use `@BindParam` when external contracts use different names.
7. **Post-binding validation**: `@Valid`/`@Validated` and properly placed `BindingResult`; verify permissions/policies in the service before saving.
8. **Test adversarial scenarios**: unknown fields, privileged fields, nested paths, type mismatches, null/missing values, pre-existing model objects, and separate-pipeline JSON endpoints.
9. **Evaluate the final object** before use: never allow a target with binding errors to proceed into data writes.

A sound design only needs to answer three questions: **which values is the constructor responsible for creating; which properties are setters permitted to modify; and after both steps, who validates the object before executing business logic?**

## Official References

- [Spring Framework 6.2 – Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html): constructor binding, property binding, combining both, and target construction mechanisms.
- [Spring Framework 6.2 – @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): attribute creation sources, constructor/property binding, BindParam, and BindingResult.
- [Spring Framework 6.2 – Web MVC Data Binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html): model design, allowedFields, declarative binding, and mass assignment protection.
- [Spring Framework 6.2 – @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html): configuring WebDataBinder in controllers.
- [Spring Framework 6.2 – DataBinder JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html): `setDeclarativeBinding`, `setAllowedFields`, `setTargetType`, `construct`, `bind`, and `getBindingResult`.
