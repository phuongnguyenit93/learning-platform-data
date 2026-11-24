# Data Sources, Field Names, and Raw Input Values in Spring MVC Data Binding

When Spring MVC receives an HTTP request, data from the client does not automatically become Java properties. The framework must determine **where the data lives**, **which name is used to look up the data**, **what the initial value is**, and **which controller parameter or object property will receive that value**. This is the first step of the data binding flow, occurring before the application uses the data and typically before validation of the bound object.

## 1. Distinguishing the Four Concepts

| Concept | Meaning | Example |
| --- | --- | --- |
| Data source (*source*) | Location containing the request input | Query string `?page=2`, form body, path variable, header, JSON body |
| Field/parameter name (*field/parameter name*) | Key used to look up the value; for property binding this is typically a JavaBeans property path | `age`, `address.city`, `tags[0]` |
| Raw input value (*raw input value*) | Data sent by the client, usually strings in query/form | `"23"`, `"Da Nang"` |
| Binding target (*target*) | Method parameter or property on a model object after type conversion | `int page`, `ProfileForm.age` of type `Integer` |

For example, from the request:

```http
POST /profiles/form?campaign=web HTTP/1.1
Content-Type: application/x-www-form-urlencoded

fullName=Lan+Anh&age=23&address.city=Da+Nang&tags%5B0%5D=java&tags%5B1%5D=spring
```

After decoding the form, Spring can see the name/value pairs:

| Submitted name | Decoded value | Potential receiving target |
| --- | --- | --- |
| `fullName` | `Lan Anh` | `ProfileForm.fullName: String` |
| `age` | `23` (string) | `ProfileForm.age: Integer` (number 23 after conversion) |
| `address.city` | `Da Nang` | `ProfileForm.address.city` |
| `tags[0]`, `tags[1]` | `java`, `spring` | Two elements of `ProfileForm.tags` |
| `campaign` in query string | `web` | `@RequestParam("campaign") String campaign` |

Key point to remember: the name `campaign` does not automatically become a property of `ProfileForm`. Each name is applied according to **how the controller declares its parameters** and **the structure of the target object**. The value `23` in the form starts as text; only after conversion succeeds is there an `Integer 23`.

## 2. Data Sources Spring MVC Can Read

In Spring MVC running on the Servlet stack, not every source goes through the same mechanism.

| HTTP source | Example | Common way to receive | Things to note |
| --- | --- | --- | --- |
| Query parameter | `GET /search?page=2` | `@RequestParam("page") int page` | Query parameters belong to the Servlet *request parameters* set |
| Form URL-encoded body | `name=An&age=23` | `@RequestParam` or `@ModelAttribute` | An `application/x-www-form-urlencoded` body is parsed into request parameters |
| Text field in multipart | `multipart/form-data`, part `name` | `@RequestParam` or form object | Requires appropriate multipart support configuration |
| Uploaded file | part `avatar` | `@RequestParam MultipartFile`, `@RequestPart` or form property | A file value is not an ordinary text string |
| URL path variable | `/users/42` with `/{id}` | `@PathVariable("id") Long id` | Extracted from URL matching, not a query parameter |
| HTTP header | `X-Region: vi` | `@RequestHeader("X-Region") String region` | Header names and property names should not be conflated |
| Cookie | `Cookie: locale=vi` | `@CookieValue("locale") String locale` | Read via the corresponding cookie argument resolver |
| JSON/XML body | `{"age":23}` | `@RequestBody ProfilePayload` | `HttpMessageConverter` deserializes the body; not the form property binding mechanism |
| JSON part in multipart | Part with `Content-Type: application/json` | `@RequestPart` | Each part can be converted by a message converter |

**Important detail about `@ModelAttribute`:** Spring MVC can use request parameters (query + form), URI path variables, and request headers as binding sources. When names collide, path variables and headers are not used to override a request parameter with the same name; header names are processed according to specific rules (for example stripping hyphens). In business code, use `@PathVariable`/`@RequestHeader` when you want a specific source, instead of relying on this supplemental mechanism.

**Difference between form and JSON:** `@ModelAttribute` typically works with flat name/value sets like `address.city=Da+Nang`. With `@RequestBody` and JSON, the client sends nested JSON structures like `{"address":{"city":"Da Nang"}}`; Jackson or the corresponding converter creates the object from the body. Both can be validated afterward, but how the input is read and the types of read/conversion errors differ.

## 3. How Field Names Are Matched to Java Properties

With **property binding**, the submitted name is a *property path* following JavaBeans conventions. Spring uses property access mechanisms (such as `BeanWrapper`), setters/getters, and appropriate conversion to assign values to the object.

| Name in form | Path on Java object | Usually required condition |
| --- | --- | --- |
| `fullName` | `form.setFullName(...)` | A writable `fullName` property exists |
| `address.city` | `form.getAddress().setCity(...)` | Appropriate `address` and `city` properties exist |
| `tags[0]` | `form.getTags().get(0)` or corresponding list element | Compatible list/array exists; binder has auto-grow limits |
| `items[1].sku` | Second element of `items`, field `sku` | Compatible element structure and element type |
| `preferences[theme]` | Map `preferences` at key `theme` | Compatible `Map` property |
| `tags=java&tags=spring` | Multiple values with the same name | Can bind into a suitable array/list or be received via `MultiValueMap` |

Commonly confused rules:

1. **HTML `name` determines the submitted field name; `id` does not replace `name`.** For example, `<input id="user-age" name="age">` is submitted with the key `age`.
2. **Model attribute name is different from field name.** `@ModelAttribute("form") ProfileForm form` names the object in the model `form`. In a typical form, the field is still `fullName`, not necessarily `form.fullName`.
3. **Names must match properties or configured renaming rules.** `user_name` does not automatically match JavaBean `userName`; you need matching form names, a custom mapper, or a mapping mechanism such as `@BindParam` for constructor binding in supported versions.
4. **Distinguish flat structure from nested structure.** In a form, `address.city` is a key representing a property path. In JSON, `address` is typically an object containing the key `city`.
5. **Client-supplied data is untrusted.** Field names can be altered with HTTP tools, including fields not shown in the UI; you must restrict which properties are allowed to bind.

## 4. Flow from Request to Java Object

```text
HTTP request
  ├─ query/form parameters: name -> one or more values
  ├─ path variables / headers / cookies: separate sources
  └─ JSON body: structured content
          |
          v
Spring MVC selects handler and argument resolver
          |
          +-- @RequestParam / @PathVariable / @RequestHeader / ... 
          |      look up name -> convert type -> controller parameter
          |
          +-- @ModelAttribute
          |      find/create model object -> WebDataBinder
          |      -> constructor/property binding -> conversion
          |      -> BindingResult -> validation when requested
          |
          +-- @RequestBody
                 HttpMessageConverter -> object
                 -> validation when requested
```

In the `@ModelAttribute` branch, you can picture it as:

1. **Select the target object.** Spring looks for an existing object in the model/session as configured, or creates a new object using an appropriate constructor. Modern Spring versions support both constructor binding and property binding.
2. **Collect values and names.** For forms, request parameters have keys like `fullName`, `age`, `address.city`. The data may contain multiple values for the same key.
3. **Resolve property paths.** With property binding, the binder matches keys against properties or nested properties; with constructor binding, it matches constructor argument names and can use `@BindParam`.
4. **Convert types.** For example, the string `"23"` becomes `Integer 23`, and a date string becomes a date according to a configured formatter. A Converter/Formatter/PropertyEditor determines how conversion works.
5. **Record binding errors.** If `age=abc` cannot be converted to a number, `BindingResult` gets a `typeMismatch` error and field info; that value should not be treated as accepted.
6. **Validation (if triggered).** `@Valid`/`@Validated` can check constraints such as `@NotBlank` or `@Min` after binding; binding errors and validation errors have different causes, even though both are represented in `BindingResult`.

**`DataBinder`** is the core component that binds names/values to an object. **`WebDataBinder`** adds capabilities needed in a web environment. **`BindingResult`** holds the errors from the binding/validation process and helps the controller return appropriate messages. A type conversion error is not the same thing as a violated Bean Validation constraint.

## 5. Complete Example in a Spring MVC Application

Suppose the application already runs Spring MVC and has a Bean Validation provider (for example, a project using `spring-webmvc` with Jakarta Validation configured). This is a Java 17+ controller you can place into that application; **this snippet is not a standalone plain Java program runnable via `javac` because it requires Spring MVC, a Servlet runtime, and related dependencies**.

**`ProfileController.java`**

```java
package demo.web;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.*;

import java.util.ArrayList;
import java.util.List;

@RestController
@RequestMapping("/profiles")
public class ProfileController {

    @PostMapping(
        path = "/form",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public ResponseEntity<String> submit(
            @Valid @ModelAttribute("form") ProfileForm form,
            BindingResult errors,
            @RequestParam(name = "campaign", required = false) String campaign) {

        if (errors.hasErrors()) {
            String fields = errors.getFieldErrors().stream()
                    .map(error -> error.getField())
                    .distinct()
                    .toList()
                    .toString();
            return ResponseEntity.badRequest().body("invalid=" + fields);
        }

        return ResponseEntity.ok(
                "name=" + form.getFullName()
                + ";age=" + form.getAge()
                + ";city=" + form.getAddress().getCity()
                + ";tags=" + form.getTags()
                + ";campaign=" + campaign
        );
    }

    public static class ProfileForm {
        @NotBlank
        private String fullName;

        @NotNull
        @Min(18)
        private Integer age;

        @Valid
        private Address address = new Address();

        private List<String> tags = new ArrayList<>();

        public String getFullName() { return fullName; }
        public void setFullName(String fullName) { this.fullName = fullName; }

        public Integer getAge() { return age; }
        public void setAge(Integer age) { this.age = age; }

        public Address getAddress() { return address; }
        public void setAddress(Address address) { this.address = address; }

        public List<String> getTags() { return tags; }
        public void setTags(List<String> tags) { this.tags = tags; }
    }

    public static class Address {
        @NotBlank
        private String city;

        public String getCity() { return city; }
        public void setCity(String city) { this.city = city; }
    }
}
```

Sample request (Bash or a shell with `curl`; assuming the server runs on port 8080):

```bash
curl -sS -X POST 'http://localhost:8080/profiles/form?campaign=web' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'fullName=Lan Anh' \
  --data-urlencode 'age=23' \
  --data-urlencode 'address.city=Da Nang' \
  --data-urlencode 'tags[0]=java' \
  --data-urlencode 'tags[1]=spring'
```

Success body (HTTP 200, text/plain):

```text
name=Lan Anh;age=23;city=Da Nang;tags=[java, spring];campaign=web
```

**Reading the result by name and target:**

- `fullName` is assigned via `setFullName`; the space in `Lan Anh` is decoded from the form.
- `age` is submitted as a string but becomes an `Integer` via conversion; `@Min(18)` checks the numeric value after binding.
- `address.city` goes into the nested `Address` object, not a literal property named `address.city`.
- `tags[0]`/`tags[1]` populate the list by index; the first index is 0.
- `campaign` is received separately by `@RequestParam`. There is no `setCampaign` setter in `ProfileForm`, so it does not become a form property.

If you send `age=abc`, the converter cannot produce an `Integer` and `errors.hasErrors()` is true; the controller returns HTTP 400 with the list of invalid fields, e.g. `invalid=[age]`. If you send `age=16`, type conversion succeeds, but `@Min(18)` produces a validation error. Both situations are inspected via `BindingResult`, with different error origins. `BindingResult` must appear **immediately after** the `@ModelAttribute` parameter being bound/validated as shown in the example.

## 6. Receiving a Single Value vs. Multiple Values

For a single parameter:

```java
@GetMapping("/search")
public String search(
        @RequestParam("q") String keyword,
        @RequestParam(name = "page", defaultValue = "1") int page) {
    return keyword + ":" + page;
}
```

Here `q` and `page` are **HTTP parameter names**, not Java variable names that are forced to match identically. The request `GET /search?q=java&page=2` returns the text `java:2` if the method is placed in a `@RestController`. `defaultValue` supplies a value when missing or empty according to `@RequestParam` semantics; you should not apply that assumption to every property in a form object.

With repeated parameters, one key can carry **multiple values**, not just one:

```http
GET /filter?tag=java&tag=spring HTTP/1.1
```

```java
@GetMapping("/filter")
public List<String> filter(@RequestParam("tag") List<String> tags) {
    return tags;
}
```

In a `@RestController`, this method returns a list containing `java` and `spring` (typically serialized as JSON). If you need to keep all keys and every raw request value, you can receive `@RequestParam MultiValueMap<String, String> params`. Using `Map<String, String>` cannot fully represent repeated values for a single key.

## 7. When Names Do Not Match, Values Are Missing, or Conversion Fails

| Situation | Possible symptom | Proper way to handle |
| --- | --- | --- |
| HTML has `id="age"` but lacks `name="age"` | Browser does not send the `age` key in the form | Set `name` to match the input contract |
| Form sends `full_name`, bean only has `fullName` | Does not bind to the expected field | Standardize names or define explicit mapping |
| Sends `address.city` but target object lacks a writable path | Field does not bind or raises error depending on config | Design DTO and nested properties properly |
| `age=abc` with `Integer` target | Type conversion error (usually `typeMismatch`) | Read `BindingResult`, return error on the right field |
| `age` is absent | Existing value may remain, or a newly created one may be `null`/default value | Distinguish *missing* from empty string and default value; add appropriate constraints |
| `age=` | Input is present but empty; conversion may yield `null` and trigger required/validation errors depending on target | Handle per API contract; avoid treating empty as always 0 |
| Sends multiple `tag` values with same name | A single string cannot represent the entire input | Use `List`/array/`MultiValueMap` when needed |
| Client sends sensitive field such as `isAdmin=true` | Risk of *mass assignment* if binding directly to an entity with setters | Only bind allowed DTOs, restrict fields |

**Do not conflate three states**: key does not exist; key exists with an empty value; key has a value that cannot be converted to the target type. Exact behavior depends on the annotation, Java type (`int` vs. `Integer`), converter, and binder configuration. For `@RequestParam`, `required=true` is the default; missing a required parameter can raise an error before the method runs. For `@ModelAttribute`, errors are usually checked via `BindingResult` if declared in the right position.

## 8. Restricting the Set of Bindable Fields

Validation checks whether data is valid; **field restriction** decides which properties the client is allowed to change. You should not bind directly to a domain entity containing properties like `role`, `balance`, or `approved` just because the frontend does not display them.

Prefer a DTO containing only allowed input fields. If using property binding, you can add a list of allowed fields:

```java
@InitBinder("form")
void configureFormBinder(WebDataBinder binder) {
    binder.setAllowedFields("fullName", "age", "address.city", "tags*");
}
```

This is a method placed in the appropriate controller (does it need import `org.springframework.web.bind.WebDataBinder`? **No**: the correct import is `org.springframework.web.bind.WebDataBinder`). `tags*` covers indexed keys such as `tags[0]`. When applied to `ProfileController` above, this method only allows property binding to the listed paths. In Spring versions supporting `setDeclarativeBinding(true)`, you can also opt for constructor-binding-only mode, allowing setter binding only when `allowedFields` is declared. Constructor binding and property binding are two different mechanisms; you need to be clear about which one you are using.

## 9. How to Self-Check the Binding Flow

When a field "does not receive its value," trace in this order:

1. Inspect the real request (URL, `Content-Type`, body, multipart) to determine the **source** and decoded name/value pairs. Do not look only at HTML or Postman UI.
2. Check the controller parameter annotation: `@RequestParam`, `@PathVariable`, `@ModelAttribute`, or `@RequestBody`. Each annotation has its own data source and processing mechanism.
3. Compare the actual name against the contract: `name` in the form; JavaBeans property path; constructor argument name and `@BindParam` if any; JSON property if using a body converter.
4. Check the target type and conversion/formatting; observe `BindingResult.getFieldErrors()`, `FieldError.getField()`, and error codes (`typeMismatch`, constraint codes).
5. Check validation constraints, `allowedFields`, nested objects, collection indices, and whether an existing value in the model might be reused.
6. When logging debug info, log only field names, error types, and non-sensitive data; avoid logging raw passwords, tokens, cookies, or private personal data.

**Mini exercise:** With a form field `name="address.city" value="Hue"`, explain why `Address.city` receives `Hue` whereas a field `name="addressCity"` does not automatically go to the same place. Then change the `age` value from `23` to `abc` and then `16`, and determine whether the error occurs at the **conversion** or **validation** step. Expected answer: the first name is a valid nested property path if the DTO supports it; `addressCity` is a different property name; `abc` causes a conversion error, while `16` converts to a number and then violates `@Min(18)`.

## Official Documentation

- [Spring MVC: @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC: @RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring MVC: Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring Core: Data Binding and property paths](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring MVC: @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
