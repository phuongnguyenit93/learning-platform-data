# Assigning Values to Constructors or Properties in Spring Data Binding

## 1. Where Does This Step Sit in the Processing Flow?

When Spring MVC receives form or query-string data for an `@ModelAttribute` parameter, the framework needs to create or obtain the target object, convert input values (usually strings) into Java types, and **assign them to the right places**. The two primary assignment mechanisms are:

- **Constructor binding:** retrieves values by constructor parameter name, converts types, and passes them into the constructor when **creating the object**. Suitable for `record` types and immutable DTOs.
- **Property binding (setter binding):** uses property names to locate writable property paths and calls setters on an **already existing object**. Suitable for JavaBeans with mutable state.

Example `POST /registrations` request with an `application/x-www-form-urlencoded` body:

```text
email=lan@example.com&age=24
```

Spring can turn the two strings `"lan@example.com"` and `"24"` into a `Registration(String email, Integer age)` via constructor, or into `setEmail(...)` and `setAge(...)` calls on a JavaBean. `"24"` must be converted from `String` to `Integer` before assignment.

Overview flow:

```text
HTTP request (form/query/path/header)
    -> select/create @ModelAttribute object
    -> read input names and values
    -> convert types via ConversionService / Formatter / PropertyEditor
    -> pass constructor arguments and/or invoke setters
    -> record type conversion / binding errors in BindingResult
    -> (if requested) run validation
    -> pass object to controller
```

This is **data binding**, which differs from dependency injection (`@Autowired`, Spring bean constructor injection) and differs from a JSON body using `@RequestBody` / `HttpMessageConverter`. In Spring MVC, binding sources for `@ModelAttribute` primarily consist of request parameters (form and query), and may also include URI variables or headers if they do not share a name with a request parameter.

## 2. Assigning Values via Constructor

### How It Works

1. Spring identifies the target class and the appropriate data constructor.
2. For each constructor parameter, it looks up the input value by **parameter name**; names can be remapped using `@BindParam`.
3. It converts each value's type, e.g., `age=24` into `Integer.valueOf(24)`.
4. It invokes the constructor to create the object. For nested objects, Spring can construct them recursively using the corresponding property paths.
5. It records any binding/conversion errors in `BindingResult`; treat the object as successfully created only when instantiation actually succeeds.

Complete controller example inside **a configured Spring MVC application**, using Java 17+ and Spring Framework 6.1+:

```java
package demo;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/registrations")
public class RegistrationController {

    public record Registration(String email, Integer age) {}

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<String> create(
            @ModelAttribute Registration registration,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body("Invalid registration");
        }

        return ResponseEntity.ok(
                registration.email() + " / " + registration.age());
    }
}
```

After starting the Spring MVC application containing the controller above:

```bash
curl -i -X POST http://localhost:8080/registrations -d "email=lan@example.com&age=24"
```

Expected **response body**:

```text
lan@example.com / 24
```

`Registration` is a `record`; its components are passed through the canonical constructor and no setters are needed. In this example, `BindingResult` catches type conversion errors such as `age=abc`, but **does not automatically check** email format or valid age unless validation rules are declared.

### Parameter Names Must Match

With a regular Java class using a parameterized constructor, parameter names must be present in bytecode metadata (typically compiled with `-parameters`) or declared via suitable mapping. When the request name differs from the Java name, use `@BindParam`:

```java
import org.springframework.web.bind.annotation.BindParam;

public record PersonInput(
        @BindParam("full-name") String fullName,
        Integer age) {}
```

Then `full-name=Lan%20Nguyen&age=24` can flow into `fullName`. `@BindParam` is a data-name mapping for constructor binding; it does not replace data validation.

**Note on constructor selection:** a class used for constructor binding should have a single clear data constructor. If multiple constructors exist, Spring's constructor selection rules may favor a default constructor when present; avoid leaving selection ambiguous. For web data cases, a `record` or a DTO with a transparent primary constructor is usually easier to understand.

## 3. Assigning Values via Properties (Property/Setter Binding)

### How It Works

1. The target object has already been created or retrieved from the model (for example via a no-arg constructor).
2. `DataBinder` uses `BeanWrapper`'s property mechanism to locate the property matching the input key.
3. It converts the value to the declared type of the setter/property.
4. It invokes setters such as `setDisplayName("Lan")`, `setAge(24)`; the new values mutate the object's state.
5. It records assignment/conversion errors in `BindingResult`.

Another controller example, also used inside a configured Spring MVC application:

```java
package demo;

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

    public static class ProfileForm {
        private String displayName;
        private Integer age;

        public ProfileForm() {}

        public String getDisplayName() { return displayName; }
        public void setDisplayName(String value) { this.displayName = value; }

        public Integer getAge() { return age; }
        public void setAge(Integer value) { this.age = value; }
    }

    @InitBinder("profileForm")
    void configureBinder(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "age");
    }

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<String> update(
            @ModelAttribute("profileForm") ProfileForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body("Invalid profile");
        }

        return ResponseEntity.ok(form.getDisplayName() + " / " + form.getAge());
    }
}
```

Try sending:

```bash
curl -i -X POST http://localhost:8080/profiles -d "displayName=Lan&age=27&role=ADMIN"
```

The expected **response body** is `Lan / 27`. The key `role` is not in the `allowedFields` list, so it is not used to set any property. Rejected fields can be inspected via `errors.getSuppressedFields()`. This example also uses a dedicated DTO with no `role` property in the DTO itself, avoiding even accidental exposure of business state.

**Do not equate a Java field with a writable property.** In default mode, `BeanWrapper` writes through JavaBean setters. A `private` field without a setter is not automatically assigned by property binding; direct field access is a separate configuration (`initDirectFieldAccess()`), not the default behavior.

## 4. Does Spring Choose Constructor or Property Binding?

| Criterion | Constructor binding | Property binding |
| --- | --- | --- |
| Timing | During object creation | After the object exists |
| Assignment target | Constructor parameters | Setters / writable properties |
| Suitable design | `record`, immutable DTO | Mutable JavaBean |
| Needs setters? | No | Usually yes |
| Name source | Parameter names, optionally `@BindParam` | Property names / property paths |
| Modifying state after creation | Not via setters if immutable | Can mutate multiple properties |
| Input boundary | Only declared constructor parameters | Must restrict the set of writable properties |

**Common point of confusion:** `@ModelAttribute` **can use both by default**: Spring creates the object via constructor (when needed), and then applies property binding to writable properties. Therefore, having a constructor **does not mean** all setters are automatically disabled. With an immutable DTO, there are no setters to assign further; with a mutable DTO, you must control which properties can be assigned.

At the core layer, `DataBinder` clearly exposes both operations:

- Constructor: create a binder with an initial `null` target, set `targetType`, then call `construct(ValueResolver)`. `ValueResolver` provides values by parameter name.
- Property: create a binder with an existing object, then call `bind(PropertyValues)` to set properties.

Example of direct property binding via `DataBinder` (this snippet uses the `ProfileForm` class defined above and requires Spring on the classpath):

```java
import java.util.Map;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

ProfileController.ProfileForm form = new ProfileController.ProfileForm();
DataBinder binder = new DataBinder(form);
binder.setAllowedFields("displayName", "age");
binder.bind(new MutablePropertyValues(
        Map.of("displayName", "Mai", "age", "29")));

if (!binder.getBindingResult().hasErrors()) {
    System.out.println(form.getDisplayName() + " / " + form.getAge());
}
```

Expected printed output when run in a Java program with Spring dependencies:

```text
Mai / 29
```

This direct snippet is a **snippet meant to be placed inside a method**; it is not a standalone Java file. It shows that `DataBinder.bind(...)` accepts property/value pairs, and the result is that setters on the same `form` object are invoked.

## 5. Nested Paths, Lists, and Type Conversion

Key names are a crucial part of assigning values:

| Input key | Meaning |
| --- | --- |
| `name` | Property `name` or constructor parameter `name` |
| `address.city` | Property `city` of object `address` |
| `lines[0].sku` | `sku` of the first element in list `lines` |
| `labels[home]` | Element corresponding to key `home` in a `Map` |

For example, a form with `address.city=Hanoi`: with property binding, the binder traverses the `address` property and assigns `city`; with constructor binding, if the `address` parameter is an object supporting construction from corresponding parameters, Spring can build the nested object. Do not assume every arbitrary collection or object will auto-instantiate successfully: it depends on data types, constructors/setters, key names, and binder configuration.

Type conversion runs prior to assignment, for instance:

- `"29"` → `Integer 29`; sending `"xyz"` into an `Integer` produces a type error.
- Date strings can be converted to `LocalDate` if a corresponding converter/formatter exists, such as `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)`.
- Collection values can go through indexed keys or supported conversions.

`ConversionService`, `Converter`, `Formatter`, and `PropertyEditor` control how type conversion works. `@InitBinder` lets you register custom settings per controller or model attribute. **Being able to parse a string does not mean the string is business-valid**; appropriate validation is still needed after binding.

## 6. When Do Binding and Validation Errors Appear?

**Binding/conversion** answers: "Can the input be placed into the right type and location?" **Validation** answers: "Do the post-binding values satisfy the constraints?"

Distinguishing examples:

- `age=abc` with an `Integer` property: **type conversion/binding error**.
- `age=-5`: still converts to `Integer -5`; only rejected if there is a rule like `@Min(0)` or a corresponding validator.
- `email=`: with `String`, this can be an empty string; to require a non-blank value, you need `@NotBlank` or another check.
- Field outside `allowedFields`: may be excluded/suppressed without necessarily producing `hasErrors() == true`. If you want to return an error when a client tries to set an unpermitted field, check `getSuppressedFields()`.

You can request Bean Validation and capture errors directly in the controller:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;

// Placed in the DTO:
public record CheckedRegistration(
        @NotBlank String email,
        @Min(0) Integer age) {}

// Placed in the handler signature:
public String submit(
        @Valid @ModelAttribute CheckedRegistration input,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "form-with-errors";
    }
    return "success";
}
```

This is a **contextual illustration**, consisting of a record declaration and a method signature, meant to be placed in an appropriate class/controller. `@Valid` requires a configured Bean Validation provider; it does not replace type conversion error handling. `BindingResult` must sit **immediately after** its corresponding `@ModelAttribute` argument. If you do not accept `BindingResult` and binding/validation fails, Spring MVC handles the error through its standard exception mechanism (such as `MethodArgumentNotValidException` in applicable cases).

## 7. Safety When Receiving Untrusted Data

Property binding is powerful, but it can cause **mass assignment/over-posting** if you expose an entity containing sensitive attributes directly as the target. For example, an entity has `role`, `approved`, `price`: a client can submit those property names as well if they are writable and unrestricted.

How to handle it:

1. **Prefer a dedicated request DTO**, containing only values the client is allowed to send; use `record`/constructor binding when reasonable.
2. With property binding, declare `binder.setAllowedFields("displayName", "age")` to accept only expected fields. Do not rely solely on a denylist, since it is hard to keep up with newly added properties.
3. You can call `binder.setDeclarativeBinding(true)` (Spring Framework 6.1+) to allow constructor binding only by default; property binding runs only if appropriate `allowedFields` are configured. This is a useful option when binding needs to be strictly declarative.
4. After binding and validation succeed, **the service decides** server-owned values such as IDs, roles, and approval status; the controller does not trust those values from the request.
5. For forms updating an existing object, control both **permission to edit the object** and **permission to edit each property**, because binding itself is not an authorization mechanism.

Example allowing only constructor binding in a controller:

```java
@InitBinder
void constructorOnly(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

The snippet above belongs inside a `@Controller`/`@RestController` class (and requires importing `WebDataBinder`, `InitBinder`). If you want some properties to remain writable, combine `setAllowedFields(...)` with this setting.

## 8. Common Mistakes and How to Check

- **Request name does not match Java name:** `full-name` differs from `fullName`; use `@BindParam` on the constructor parameter or fix the form key.
- **Missing constructor name metadata:** for regular classes, compile with `-parameters` when needed. For example, `javac -parameters MyDto.java` if compiling a plain Java DTO; a Spring application still requires its separate dependencies.
- **Expecting setters to run on a record:** records do not have JavaBean setters; values enter a record primarily via its constructor.
- **Assuming having a constructor disables setter binding:** Spring MVC can combine both by default; design for immutability or configure the binder to lock it down.
- **Using private fields without setters:** by default, property binding cannot automatically set a private field just because names match.
- **Sending JSON and expecting `@ModelAttribute` to behave like `@RequestBody`:** JSON bodies take a different path, typically via Jackson/`HttpMessageConverter`.
- **Thinking `@Valid` performs type conversion:** type conversion happens during binding; validation applies validity rules on the data.
- **Not placing `BindingResult` right next to the bound object:** Spring may fail to associate errors as expected.
- **Binding entities directly:** opens paths to modifying unintended fields; prefer DTOs and restrict allowed fields.

### Quick Self-Check Table

| Request / target | What to observe |
| --- | --- |
| `email=lan@example.com&age=24` → `Registration` record | Constructor receives `String` and `Integer 24` |
| `displayName=Lan&age=27` → `ProfileForm` | Setters write name and age |
| `age=abc` | `BindingResult.hasErrors()` due to failed type conversion |
| `role=ADMIN` in the `ProfileController` example | No `role` property permitted to bind; check suppressed fields |
| `full-name=Lan` → `@BindParam("full-name")` | Data goes into parameter `fullName` |
| `age=-5` with `@Min(0)` and `@Valid` | Numeric type binding succeeds, validation fails |

**Remember:** constructor binding governs which data participates in **creating the object**; property binding governs which data can **mutate the object** after creation. Both depend on key names, type conversion, and error handling; for client-supplied data, the assignable scope must be explicitly designed.

## References

- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring MVC — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC — Data Binding / Model Design](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring MVC — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
