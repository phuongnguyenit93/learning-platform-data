# Records and Immutable Objects Using Constructor Binding in Spring MVC

## 1. The Problem: Creating Input Objects Without Setters

In a Spring MVC application, an HTTP request commonly carries string-based data such as `display-name=Mai`, `age=25`, `address.city=Hue`. The controller needs a strongly typed Java object to process that data. The traditional JavaBean approach calls an empty constructor and then sets each property via a setter. With a **Java record** or an immutable class, however, values are supplied at initialization time and there are no setters.

**Constructor binding** solves this problem: Spring locates a suitable data constructor, retrieves request values by parameter name, converts types, and invokes the constructor to build the object. With Java 17+ records, the canonical constructor is derived from the record components, making records especially well suited for representing input data.

Expected outcomes after this lesson:

- Distinguish constructor binding from property/setter binding.
- Write a record and an immutable class as a `@ModelAttribute`.
- Understand how parameter names, `@BindParam`, type conversion, nested data, and validation work together.
- Handle errors through `BindingResult` and prevent binding unintended fields.
- Distinguish MVC form constructor binding from `@RequestBody` JSON deserialization.

Primary illustrative scope: **Java 17+, Spring Framework 6.1/6.2 (Spring Boot 3.x), Spring MVC Servlet**. Some mechanisms have minor differences in other versions; always verify the API for your project's exact version.

## 2. Two Binding Paths and Choosing an Object Type

Suppose a client submits the form:

~~~text
display-name=Mai
age=25
address.city=Hue
address.street=Le Loi
~~~

With **property binding**, an application typically uses a mutable JavaBean:

~~~java
public class ProfileBean {
    private String displayName;
    private Integer age;

    public ProfileBean() {}

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String value) { this.displayName = value; }

    public Integer getAge() { return age; }
    public void setAge(Integer value) { this.age = value; }
}
~~~

Here Spring can instantiate `ProfileBean` and call the corresponding setters. This snippet only illustrates a JavaBean, not a complete application.

With **constructor binding**, you can declare a record:

~~~java
public record ProfileInput(String displayName, Integer age) {}
~~~

Spring identifies constructor parameters `displayName` and `age`, converts `"25"` into `Integer`, and instantiates `new ProfileInput("Mai", 25)`. No empty constructor or setters are needed. A record provides accessors `displayName()` and `age()` rather than generating `getDisplayName()` or `setDisplayName()`.

| Characteristic | Mutable JavaBean | Record / Immutable Class |
| --- | --- | --- |
| Typical instantiation | Empty constructor then setters | Constructor accepting data |
| Post-instantiation mutation | Properties can be changed | `final` components cannot be changed via setters |
| Defining allowed input | May expose many setters | Expressed directly in constructor signature |
| Risk of binding unintended properties | Requires controlling setters/allowed fields | Restricted via constructor parameters; still check nested objects |
| Validation | Uses `@Valid`/`@Validated` | Also uses `@Valid`/`@Validated` |

Important point: **a record does not automatically make the entire structure deeply immutable**. A record holding a mutable `List` can still expose that list for callers to mutate. Section 8 addresses this issue.

## 3. At Which Step Does Spring MVC Invoke the Constructor?

When a handler declares a `@ModelAttribute` parameter and no matching object exists in the model yet, Spring MVC can create the object from a default constructor or a primary/data constructor. For records, the canonical constructor is the appropriate path.

~~~text
Request params / form fields / URI variables / headers
                          |
                          v
     Resolve @ModelAttribute and get/create binder
                          |
                          v
     @InitBinder configures WebDataBinder if present
                          |
                          v
     Locate data constructor and parameter names
                          |
                          v
     Look up input values, convert each parameter type
                          |
                          v
     Invoke constructor to build record/immutable object
                          |
                          v
     Property binding if still permitted
                          |
                          v
     @Valid / @Validated (when requested)
                          |
                          v
     BindingResult -> controller or MVC exception
~~~

This is a conceptual flow; do not treat it as a guarantee that every handler must instantiate a new object. A `@ModelAttribute` may already exist in the model/session or be obtained via a converter, in which case object retrieval differs from constructor instantiation.

For the core `DataBinder`, Spring clearly distinguishes:

- **Constructor binding:** maps input data to *constructor parameters*, potentially recursively creating nested objects.
- **Property binding:** assigns values to *writable properties*, such as setters.
- **Type conversion:** converts request strings into `Integer`, `LocalDate`, enums, or other types via `ConversionService` / formatters.
- **Validation:** checks constraints after binding when triggered by `@Valid` or similar.

Spring MVC normally applies both constructor and property binding. Simply using a setterless record limits which components can be modified, but you should not assume the entire property binding phase is disabled. Section 9 shows how to explicitly configure constructor-only binding.

## 4. Complete Example: Form Request into an Immutable Record

Create a Spring Boot 3.x application with Java 17 or newer from Spring Initializr and select the **Spring Web** and **Validation** dependencies. With Gradle Groovy, the main dependencies in `build.gradle` are:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

A project generated by Spring Initializr already manages the Spring Boot plugin version and Java configuration; do not add child library versions manually that conflict with the project's BOM.

### 4.1. File `src/main/java/com/example/binding/BindingApplication.java`

~~~java
package com.example.binding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingApplication.class, args);
    }
}
~~~

### 4.2. File `src/main/java/com/example/binding/CreateProfileForm.java`

~~~java
package com.example.binding;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.web.bind.annotation.BindParam;

public record CreateProfileForm(
        @BindParam("display-name")
        @NotBlank String displayName,

        @NotNull @Min(18) Integer age,

        @Valid @NotNull Address address
) {
    public record Address(
            @NotBlank String city,
            String street
    ) {}
}
~~~

In this DTO:

1. `displayName` is the Java component name; `@BindParam("display-name")` instructs constructor binding to read the input named `display-name`.
2. `age` has type `Integer` so the converter can turn `"25"` into the number `25`. `@NotNull` prevents age from being omitted; `@Min(18)` checks the lower bound.
3. `address` is a nested record type. From `address.city=Hue` and `address.street=Le Loi`, constructor binding can construct `Address("Hue", "Le Loi")` and pass it into `CreateProfileForm`'s constructor.
4. `@Valid` on the `address` component asks validation to cascade into the nested object; `@NotNull` requires the nested object to exist. `@NotBlank` on `city` protects the required field.

Neither `CreateProfileForm` nor `Address` has setters. After initialization, data is read via `form.displayName()`, `form.age()`, `form.address().city()`.

### 4.3. File `src/main/java/com/example/binding/ProfileController.java`

~~~java
package com.example.binding;

import jakarta.validation.Valid;
import java.util.Map;
import java.util.Objects;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/profiles")
public class ProfileController {

    @InitBinder("form")
    void configureFormBinder(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> create(
            @Valid @ModelAttribute("form") CreateProfileForm form,
            BindingResult errors
    ) {
        if (errors.hasErrors()) {
            var messages = errors.getFieldErrors().stream()
                    .map(error -> Map.of(
                            "field", error.getField(),
                            "code", Objects.toString(error.getCode(), "invalid"),
                            "message", Objects.toString(
                                    error.getDefaultMessage(), "Invalid")
                    ))
                    .toList();
            return ResponseEntity.badRequest()
                    .body(Map.of("errors", messages));
        }

        return ResponseEntity.ok(Map.of(
                "displayName", form.displayName(),
                "age", form.age(),
                "city", form.address().city()
        ));
    }
}
~~~

`@InitBinder("form")` configures the binder only for the model attribute named `form`. Calling `setDeclarativeBinding(true)` enables a mode in which constructor binding always applies, while setter binding only takes effect if `allowedFields` is explicitly configured. This example does not declare `allowedFields`, so the input is built strictly through its constructor. Do not add setters to bypass a record's immutability.

`@Valid` on `@ModelAttribute("form")` triggers Bean Validation after the object is bound. `BindingResult errors` must appear **immediately after** the bound/validated parameter. If errors exist, the controller returns HTTP 400; on success, it returns HTTP 200 with the converted input data.

### 4.4. Running and Testing Requests

From the project root containing the Gradle Wrapper, run:

~~~bash
./gradlew bootRun
~~~

On Windows, use `gradlew.bat bootRun`. For a Maven-based project, use the corresponding Maven command.

Send a valid form in a terminal with `curl`:

~~~bash
curl -i -X POST http://localhost:8080/profiles -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "display-name=Mai" --data-urlencode "age=25" --data-urlencode "address.city=Hue" --data-urlencode "address.street=Le Loi"
~~~

The expected HTTP status is **200 OK**. The JSON body has equivalent content (JSON property order is not guaranteed):

~~~json
{"displayName":"Mai","age":25,"city":"Hue"}
~~~

Try values that can be type-converted but are invalid:

~~~bash
curl -i -X POST http://localhost:8080/profiles -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "display-name=" --data-urlencode "age=17" --data-urlencode "address.city="
~~~

The expected result is **400 Bad Request**, with field errors reported for `displayName`, `age`, and `address.city`. Error codes and messages can vary by validator provider, message source, and locale, so do not assume the error array has a fixed order.

Try a constructor parameter type-conversion error:

~~~bash
curl -i -X POST http://localhost:8080/profiles -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "display-name=Mai" --data-urlencode "age=abc" --data-urlencode "address.city=Hue"
~~~

`age=abc` cannot be converted into `Integer`. This is a **binding/conversion error**, which can be reflected in `BindingResult` (typically with code `typeMismatch`), rather than `@Min(18)` running on the string `abc`. Depending on the instantiation path and error handling, Spring can turn the error into an exception if the controller does not declare a matching `BindingResult`.

## 5. Why Do Constructor Parameter Names Matter?

Constructor binding does not look for setters; it must resolve pairs of **input name → constructor parameter**. By default, names are read from parameter metadata stored in bytecode. For records, the canonical constructor explicitly states component order and names. For regular Java classes, compile with parameter-name metadata—typically the `-parameters` compiler flag—if you want Spring to match by name; Spring Boot build tooling normally supports configuring this.

With Gradle, you can declare it explicitly:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += '-parameters'
}
~~~

Add this Groovy snippet to `build.gradle` if the current build does not already enable that flag; there is no need to duplicate it if the project already configures it.

HTTP parameter names are sometimes invalid as Java identifiers (for example, `display-name`). Use `@BindParam` on the constructor parameter or corresponding field to map it:

~~~java
public record SearchForm(
        @BindParam("search-text") String text,
        Integer page
) {}
~~~

Here `search-text=java` maps to `text`, and `page=2` maps to `page`. `@BindParam` is an annotation **for Spring DataBinder constructor binding** and does not automatically rename JSON keys when using Jackson. If a JSON endpoint wants the key `search-text`, configure JSON mapping separately, such as `@JsonProperty("search-text")`.

Note that multiple constructors or auxiliary constructors on an immutable class can make constructor selection ambiguous. Design a single, public data constructor where appropriate; a record's canonical constructor is a convenient choice.

## 6. Immutable Classes Are Possible Without Records

Using a record is not mandatory. A `final` class with `private final` fields and an all-arguments constructor also works with constructor binding:

~~~java
package com.example.binding;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.web.bind.annotation.BindParam;

public final class CreateTeamForm {
    private final String teamName;
    private final Integer size;

    public CreateTeamForm(
            @BindParam("team-name") String teamName,
            Integer size
    ) {
        this.teamName = teamName;
        this.size = size;
    }

    @NotBlank
    public String getTeamName() {
        return teamName;
    }

    @NotNull
    public Integer getSize() {
        return size;
    }
}
~~~

This is a standalone Java file that compiles in a project containing the dependencies listed in section 4; to use it in a handler, declare `@Valid @ModelAttribute CreateTeamForm form` with `BindingResult` in the proper position. It has no empty constructor or setters. `@BindParam("team-name")` maps `team-name` to `teamName`.

Placing Bean Validation constraints on getters is a valid way to validate object state after instantiation; constraints can also be placed on fields. `@Valid` is still required to trigger validation when the handler receives the form.

Choose a record for pure data when you want minimal boilerplate. Choose an immutable class when you need API control, internal behavior, or have design constraints that do not fit a record.

## 7. Nested Objects, Collections, and Formatters in Constructor Binding

Constructor binding is not limited to flat fields. Spring can construct nested objects from field paths:

~~~java
public record AddressInput(String city, String district) {}

public record ContactInput(String name, AddressInput address) {}
~~~

With request parameters `name=Lan`, `address.city=DaNang`, `address.district=HaiChau`, Spring can create `ContactInput("Lan", new AddressInput("DaNang", "HaiChau"))`.

It also supports collections, maps, and arrays via indexed keys, for example:

~~~java
public record LineInput(String sku, Integer quantity) {}

public record BasketInput(java.util.List<LineInput> items) {}
~~~

Fields `items[0].sku=BOOK`, `items[0].quantity=2`, `items[1].sku=PEN`, `items[1].quantity=3` represent two elements. These are **type definitions and key examples**, not a complete MVC application; to validate nested data, add appropriate Bean Validation annotations (for instance `@Valid` on the collection/elements and `@Size` to bound element count).

Do not assume that element counts, nesting depth, or external input sizes are always safe. Bound which collections are accepted, limit request size, and control binding of sensitive fields.

For date/time parameters, you can use a formatter:

~~~java
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;

public record VisitForm(
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate visitDate
) {}
~~~

This snippet shows using `2026-11-02` as the corresponding form value. `LocalDate` is the target type, while `@DateTimeFormat` helps Spring choose the conversion format. When input has the wrong format, the error happens during the conversion/binding phase, prior to business validation.

## 8. Shallow Immutability of Records: Protecting Collections and Nested Data

In Java, record component fields are `final`, but **`final` only freezes the reference**, not the mutability of the referenced object inside. For example, `record Filters(List<String> tags) {}` can still hold an `ArrayList` that gets modified after the record is created.

You can perform a defensive copy in a compact canonical constructor. The pure Java snippet below **compiles and runs standalone on Java 17+**, without Spring.

File `RecordCopyDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RecordCopyDemo {
    record Filters(List<String> tags) {
        Filters {
            tags = List.copyOf(tags);
        }
    }

    public static void main(String[] args) {
        var original = new ArrayList<>(List.of("java"));
        var filters = new Filters(original);

        original.add("spring");
        System.out.println(filters.tags());

        try {
            filters.tags().add("mvc");
        } catch (UnsupportedOperationException ex) {
            System.out.println("List cannot be modified");
        }
    }
}
~~~

Run:

~~~bash
javac RecordCopyDemo.java
java RecordCopyDemo
~~~

Exact stdout:

~~~text
[java]
List cannot be modified
~~~

`List.copyOf` creates an unmodifiable snapshot of the list, so mutating `original` does not affect `filters.tags()`. It also rejects `null` elements; define appropriate `null`-handling rules when building DTOs from external data.

A record holding a mutable JavaBean field still needs attention: although the reference cannot be reassigned, a caller can still mutate the nested object's state. To preserve deep immutability, use immutable nested objects and appropriate defensive copies.

Avoid putting complex logic or unexpected exceptions inside a constructor as a replacement for validation. For instance, throwing `IllegalArgumentException` when age is below 18 can fail instantiation before Bean Validation records field errors in `BindingResult`. For ordinary input errors, use constraints like `@Min` and process `BindingResult` to produce per-field messages.

## 9. Controlling Setter Binding and Avoiding Mass Assignment

An HTTP request is **untrusted** input. An entity like `UserEntity` might contain fields such as `role`, `enabled`, `ownerId`; binding that entity directly from a request creates the risk that a client submits unexpected extra properties.

A safe design uses a **dedicated input DTO**, with a constructor containing only the values the client is permitted to supply. After validation, the service maps the DTO onto domain objects and populates server-owned values itself.

Because Spring MVC supports both constructor and property binding by default, you can require constructor-only binding for a model attribute:

~~~java
@InitBinder("form")
void configureFormBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
~~~

The snippet above is a controller fragment; import `org.springframework.web.bind.annotation.InitBinder` and `org.springframework.web.bind.WebDataBinder`. `setDeclarativeBinding(true)` means:

- Constructor binding continues to work for the parameters declared by the constructor.
- Setter/property binding only works when an `allowedFields` list is explicitly declared.
- Enabling this mode **does not replace** validation, authorization, data-type checks, or business rules.

If you need to apply this across multiple controllers, you can configure it via `@ControllerAdvice` and `@InitBinder`, while checking its impact on other forms that rely on property binding. When setters are still needed, declare `binder.setAllowedFields("firstName", "lastName")` to explicitly limit writable fields.

For example, suppose someone sends `role=ADMIN` to `CreateProfileForm` in section 4: the `role` component does not exist in the data constructor and the binder is configured declaratively, so the controller will not use it to alter roles. **Extra fields do not necessarily trigger an automatic 400**; if the API requires rejecting undeclared inputs, add a separate request-verification policy.

Do not treat a record or final class as an authorization mechanism. An immutable DTO can still contain sensitive fields if the developer puts them into the constructor; write authority over those fields must be governed by API design and the business layer.

## 10. Validation and `BindingResult` with Constructor Binding

Constructor binding is responsible for **creating a typed object**, while Bean Validation is responsible for **checking constraints after binding**. Placing constraints on record components alone is not enough to trigger validation automatically on every handler. With `@ModelAttribute`, declare `@Valid` or `@Validated` on the controller parameter:

~~~java
@PostMapping("/example")
public String handle(
        @Valid @ModelAttribute("form") CreateProfileForm form,
        BindingResult errors
) {
    if (errors.hasErrors()) {
        return "profile-form";
    }
    return "success";
}
~~~

This is a **fragment** of a controller rendering an MVC view, not a replacement for the `@RestController` example in section 4.

Two error forms to distinguish:

| Input | Phase / Outcome |
| --- | --- |
| `age=25` | String converts to `Integer 25`; satisfies `@Min(18)`. |
| `age=17` | Constructor binding may succeed; Bean Validation detects less than 18. |
| `age=abc` | Conversion to `Integer` fails; binding/conversion error, typically coded `typeMismatch`. |
| `display-name=` | String parameter is read; `@NotBlank` detects blank text. |
| Missing `address.city` | Nested object or its property is incomplete; `@NotNull` and `@NotBlank` record appropriate errors when validation runs. |

`BindingResult` can hold both `FieldError` and `ObjectError` entries. You can inspect `errors.getFieldErrors()`, `errors.getFieldError("age")`, `errors.hasFieldErrors("address.city")`, and `errors.hasErrors()`. Depending on the error, `getRejectedValue()` may expose the invalid request value; avoid logging sensitive data or leaking it in public responses.

`BindingResult` must sit immediately after the parameter it describes. If this argument is missing, Spring MVC typically turns `@ModelAttribute` validation failures into `MethodArgumentNotValidException`; in handlers where method validation applies to constraints placed directly on parameters, the exception can be `HandlerMethodValidationException`. Do not catch every HTTP 400 generically and assume all of them are constructor errors.

Special note: a constructor can throw an exception itself when data is invalid (for example `Objects.requireNonNull(...)` or an invariant check). In that case the object may never be constructed, and the handling flow differs from constraint errors routed through `BindingResult`. Reserve constructor invariants for truly unbreakable structural rules; for expected user-input errors, prefer the validator system.

## 11. Differences from `@RequestBody` and JSON

Both may use a Java record, yet the two ways of receiving requests go through different mechanisms.

- **`@ModelAttribute` + form/query:** Spring MVC uses `WebDataBinder` to create the model attribute via constructor binding and (if enabled) property binding.
- **`@RequestBody` + JSON:** `HttpMessageConverter`, typically Jackson, deserializes JSON into the record using the JSON library's constructor-mapping support. This is **not** `DataBinder`'s constructor binding flow for request parameters.

Example handler fragment receiving JSON:

~~~java
@PostMapping(path = "/json",
             consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<?> createJson(
        @Valid @RequestBody CreateProfileForm request,
        BindingResult errors
) {
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body("Invalid data");
    }
    return ResponseEntity.ok("accepted");
}
~~~

This is an illustrative snippet within a controller that has matching imports. Typical JSON:

~~~json
{
  "displayName": "Mai",
  "age": 25,
  "address": {
    "city": "Hue",
    "street": "Le Loi"
  }
}
~~~

Note that `@BindParam("display-name")` on the DTO does not automatically make Jackson look for the `"display-name"` key; to rename JSON properties, use Jackson's annotations or naming strategy, such as `@JsonProperty`.

If the JSON is malformed or cannot be deserialized, Spring typically raises `HttpMessageNotReadableException` before validation. If JSON produces an object that violates constraints without an inline `BindingResult`, `MethodArgumentNotValidException` is typically raised. Properly distinguishing these two stages helps you choose the right error codes and messages.

## 12. Testing Constructor Binding Instead of Only Testing the Java Constructor

Writing a unit test that calls `new CreateProfileForm(...)` only proves the Java constructor works; it **does not prove** Spring maps field names, handles `@BindParam`, constructs nested records, converts types, and runs validation. Use `MockMvc` to go through Spring MVC:

File `src/test/java/com/example/binding/ProfileControllerTest.java`:

~~~java
package com.example.binding;

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
    void bindNestedImmutableRecordsSuccessfully() throws Exception {
        mvc.perform(post("/profiles")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("display-name", "Mai")
                    .param("age", "25")
                    .param("address.city", "Hue")
                    .param("address.street", "Le Loi"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value("Mai"))
                .andExpect(jsonPath("$.age").value(25))
                .andExpect(jsonPath("$.city").value("Hue"));
    }

    @Test
    void rejectBusinessConstraintViolations() throws Exception {
        mvc.perform(post("/profiles")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("display-name", "")
                    .param("age", "17")
                    .param("address.city", ""))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectConstructorArgumentConversionError() throws Exception {
        mvc.perform(post("/profiles")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("display-name", "Mai")
                    .param("age", "not-a-number")
                    .param("address.city", "Hue"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Run via Gradle Wrapper:

~~~bash
./gradlew test --tests com.example.binding.ProfileControllerTest
~~~

On Windows: `gradlew.bat test --tests com.example.binding.ProfileControllerTest`. The three tests distinguish: (1) constructor binding + nested record + parameter renaming; (2) constraint errors; (3) conversion errors. Under different MVC configurations or Spring versions, verify actual responses and exceptions rather than assuming every error produces identical JSON.

You can add a test sending `role=ADMIN` to verify the DTO ignores that field and authorization is decided by the service. If your configuration intentionally permits property binding, also test fields outside `allowedFields`.

## 13. Common Mistakes

1. **Assuming records must have an empty constructor.** Records do not need setters or a no-arg constructor in constructor binding. Spring creates the object using the canonical/data constructor when eligible.
2. **Missing parameter-name metadata on regular classes.** Without runtime parameter names or `@BindParam`, Spring has no reliable basis to match request fields to constructor arguments. Check `-parameters` and build settings.
3. **Using request names that do not match Java names.** `display-name` and `displayName` are different keys; configure `@BindParam` in the right place and test with real requests.
4. **Confusing form constructor binding with JSON.** `@BindParam` is not `@JsonProperty`, and `@RequestBody` goes through a message converter.
5. **Assuming records are deeply immutable.** `List`, `Map`, or mutable child objects can still be modified; consider defensive copies and immutable nested DTOs.
6. **Omitting `@Valid`/`BindingResult`.** Constraints on a record only run when validation is triggered; place `BindingResult` right next to the target parameter so the controller can handle errors.
7. **Using primitive types for every required input.** For forms where values may be omitted, `Integer` + `@NotNull` usually reports errors more clearly than `int` receiving a default or context-dependent conversion failure.
8. **Throwing arbitrary business exceptions inside constructors.** A constructor that fails to instantiate an object is not equivalent to Bean Validation producing a list of `FieldError` entries. Use constraints for expected input errors and reserve constructor invariants for genuine structural rules.
9. **Binding entities with sensitive fields directly.** Constructor binding narrows the input surface, but it does not replace dedicated DTOs, authorization, and allowed-field controls.
10. **Enabling `setDeclarativeBinding(true)` application-wide without checking other forms.** Setter-based forms may stop receiving data if `allowedFields` is not declared; apply the setting to the intended scope.

## 14. Practical Checklist

When designing an input object as a record or immutable class for Spring MVC:

- Choose a DTO dedicated to HTTP input; list the exact components the client is allowed to send.
- Use a single clear data constructor; for regular classes, ensure parameter-name metadata or `@BindParam`.
- Define appropriate types (`Integer`, `LocalDate`, nested records, collections) and formatters when needed.
- Apply Bean Validation on components/fields/getters along with `@Valid`/`@Validated` on the handler; add `@Valid` to nested objects that need recursive validation.
- Place `BindingResult` immediately after `@ModelAttribute` if the controller needs to render/return errors itself.
- Consider `setDeclarativeBinding(true)` to enforce constructor-only binding, and govern property binding separately when permitted.
- Protect mutable collections with defensive copies, bound data size/depth, and never bind sensitive entities directly.
- Test via HTTP/MockMvc with valid data, missing fields, wrong types, constraint violations, and extra fields.

**Takeaway:** constructor binding builds an object from the parameters defined by its constructor; a record is a concise way to express an immutable input object. In Spring MVC, this choice works alongside validation, error handling, type conversion rules, and field restrictions to build predictable, safe APIs.

### Official References

- [Spring Framework 6.2 — `@ModelAttribute` and Constructor Binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — Core Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework — MVC Data Binding and Model Design](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — `@RequestBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
