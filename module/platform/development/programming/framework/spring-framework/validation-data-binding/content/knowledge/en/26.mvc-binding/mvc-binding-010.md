# Distinguishing `@ModelAttribute` from `@RequestBody` and `HttpMessageConverter` in Spring MVC

## 1. Both build Java objects from HTTP, yet take **two different paths**

In Spring MVC (Servlet stack), a controller can receive a Java object from a request using two familiar annotations:

~~~java
@PostMapping("/profiles/form")
String saveForm(@ModelAttribute ProfileForm form) {
    // form is created/retrieved from the model and bound from request values.
    return "ok";
}

@PostMapping("/profiles/json")
String saveJson(@RequestBody ProfileJson body) {
    // body is read using an HttpMessageConverter.
    return "ok";
}
~~~

Both are **snippets** to place inside a configured controller, not standalone compilable files. Although both accept objects, **`@ModelAttribute` is not an alias for `@RequestBody`**:

- **`@ModelAttribute`**: creates or retrieves a **model attribute**, then uses **`WebDataBinder`/`ServletRequestDataBinder`** to bind request parameters (query, form), along with URI variables/headers in MVC integration when applicable; data is mapped onto constructor arguments or JavaBean properties.
- **`@RequestBody`**: reads the **HTTP message body content** using an **`HttpMessageConverter`** matching the Java type and HTTP `Content-Type`; for example, Jackson converts a JSON object into a Java record/POJO.

Thus, a form request and a JSON request **do not differ merely in syntax**; they travel through **two distinct data-conversion, error-reporting, and security-configuration mechanisms**.

Example of two requests representing Lan's profile:

~~~http
POST /profiles/form
Content-Type: application/x-www-form-urlencoded

name=Lan&age=26&newsletter=true
~~~

~~~http
POST /profiles/json
Content-Type: application/json

{"name":"Lan","age":26,"newsletter":true}
~~~

The first request typically pairs with `@ModelAttribute` or `@RequestParam`; the second typically pairs with `@RequestBody` and a JSON converter. Choose the annotation based on the **actual HTTP data contract**, not simply whether the Java parameter is a class or a record.

## 2. Detailed comparison table

| Criterion | `@ModelAttribute` | `@RequestBody` |
| --- | --- | --- |
| Purpose | Create/retrieve a model attribute and **data-bind** request values onto it. | Read the **message body** and deserialize it into a Java value. |
| Typical data source | Query string, `application/x-www-form-urlencoded`, multipart form; MVC integration can also include URI template variables and headers. | Raw HTTP body: JSON, XML, plain text, bytes, etc., depending on converter and Java type. |
| Executing components | `ModelAttributeMethodProcessor`/`ServletModelAttributeMethodProcessor`, `WebDataBinder`, `ConversionService`, `PropertyEditor`, formatters. | `RequestResponseBodyMethodProcessor` and registered `HttpMessageConverter`s. |
| Target creation | May retrieve from Model/Session, convert by key, or call constructor; followed by constructor/property binding. | Converter creates/deserializes the object from the body (e.g., Jackson for JSON). |
| Type conversion | Spring data binding/formatters; property paths like `address.city`, `items[0].name`. | Converter and mapping library rules (e.g., Jackson JSON annotations, deserializers). |
| `Content-Type` dependency | For query/form usually relies on the request parameter map, needing no JSON converter. | Converter is selected based on HTTP media type and Java target type. |
| `@Valid` checks | Runs **after binding**; errors go into `BindingResult` or throw an exception if no local handler exists. | Runs **after successful deserialization**; malformed JSON fails before validation. |
| Conversion failure | Typically a `FieldError` with code `typeMismatch` in `BindingResult`. | Typically `HttpMessageNotReadableException` when body cannot be parsed/deserialized. |
| Unsupported media type | Form/query requests do not necessarily depend on message converters; mapping `consumes` still applies. | No matching converter for type/media type typically produces HTTP 415. |
| `BindingResult` | Can be placed **immediately after** `@ModelAttribute`; common in HTML forms. | Can be placed **immediately after** `@RequestBody` to handle *validation* errors once deserialized; does not turn JSON syntax errors into `BindingResult`. |
| Input field security | Use form DTOs, constructor binding, and `@InitBinder`/`setAllowedFields` for setter/property binding. | Use request DTOs, Jackson configuration, and authorization checks; `setAllowedFields` is not a JSON deserialization allowlist. |
| Best suited for | HTML forms, GET filters/queries, multi-field request parameters, form uploads. | JSON/XML REST APIs, raw text/bytes, or body formats supported by converters. |

**More accurately:** `@RequestBody` **does not mean “always JSON”**. It uses an `HttpMessageConverter`, which may be a JSON converter, `StringHttpMessageConverter`, `ByteArrayHttpMessageConverter`, or an XML/form converter depending on configuration. Conversely, `@ModelAttribute` is not the default mechanism for reading JSON payloads.

## 3. Internal processing flow in Spring MVC

After `DispatcherServlet` selects a handler method, `RequestMappingHandlerAdapter` uses *argument resolvers* to supply the controller arguments.

### 3.1. With `@ModelAttribute`

~~~text
HTTP request
   |
   +-- ?name=Lan&age=26
   +-- form body: name=Lan&age=26
   +-- multipart form parts
   +-- URI variables/headers if MVC integration permits
   |
   v
ServletModelAttributeMethodProcessor
   |
   +--> Find existing instance in Model / @SessionAttributes
   |    or instantiate via constructor / suitable converter
   |
   v
WebDataBinder / ServletRequestDataBinder
   |
   +--> constructor binding (if target is constructed from arguments)
   +--> property binding, Spring ConversionService/formatters
   +--> @InitBinder: allowed fields, converters, validators
   +--> BindingResult: typeMismatch, required, suppressed fields
   |
   v
@Valid / @Validated if requested
   |
   v
Controller receives object (+ BindingResult if declared immediately after)
~~~

According to MVC documentation, request parameters include **query parameters and form parameters** per the Servlet API. When MVC binds `@ModelAttribute`, URI template variables and request headers may be added provided they **do not override** same-named request parameters; header names may have hyphens stripped. This is MVC integration behavior, **not a guarantee that calling `new ServletRequestDataBinder(...).bind(request)` manually will automatically read arbitrary headers or cookies**.

Note that `@ModelAttribute` can retrieve an object already present in the model before binding, including model attributes prepared by another method or declared session attributes. Therefore, never assume every call instantiates a new object via a no-arg constructor. In modern Spring MVC, constructor binding also supports immutable DTOs/records when parameter-name metadata is available.

### 3.2. With `@RequestBody`

~~~text
HTTP request
   |
   +-- Content-Type: application/json
   +-- Body: {"name":"Lan","age":26}
   |
   v
RequestResponseBodyMethodProcessor
   |
   +--> Select suitable HttpMessageConverter:
   |      canRead(targetType, contentType)
   |
   +--> JSON converter / Jackson: deserialize body -> object
   |    (or matching String/byte[]/XML converter)
   |
   +--> @Valid / @Validated if present
   |
   v
Controller receives object (+ Errors/BindingResult when applicable)
~~~

If the body is missing when `@RequestBody(required=true)` (the default), or if the content is syntactically invalid/un-deserializable, the controller may never be called. If no converter handles the media type/target type, the request can receive HTTP 415. These failures occur during message reading, not JavaBean field binding via `WebDataBinder`.

**Note on responses:** `@ResponseBody` (and `@RestController`) uses message conversion in the **response-writing direction**, while `@RequestBody` uses it in the **request-reading direction**. Both directions share the `HttpMessageConverter` abstraction yet perform opposite roles.

## 4. `@ModelAttribute` details: objects, properties, and parameter sources

### 4.1. GET/filter scenario

~~~java
@GetMapping("/products")
String search(@ModelAttribute("filter") SearchFilter filter,
              Model model) {
    model.addAttribute("items", service.search(filter));
    return "product-list";
}
~~~

This snippet assumes `SearchFilter`/`service` exist. With request:

~~~http
GET /products?keyword=java&minPrice=100
~~~

Spring creates/retrieves `SearchFilter` and binds `keyword` and `minPrice` via property setters or constructor arguments. There is no JSON body to read. When using `int` or `BigDecimal`, Spring applies configured conversions/formatters; parse failures produce binding errors.

### 4.2. HTML form scenario

~~~html
<form method="post" action="/profiles/form">
  <input name="name" value="Lan">
  <input name="age" type="number" value="26">
  <input type="hidden" name="_newsletter" value="present">
  <input name="newsletter" type="checkbox" value="true">
  <button type="submit">Save</button>
</form>
~~~

HTTP `application/x-www-form-urlencoded` is normally parsed by the Servlet container into request parameters; Spring's data binder receives names like `name`, `age`, and `newsletter`. Field marker `_newsletter` indicates the checkbox existed on the form even if unchecked; `WebDataBinder` uses the marker to reset the value when the real field is omitted.

Nested names like `address.city` or indexed names like `items[0].quantity` can also be used. These are Spring **property paths**, distinct from JSON schemas; restrict the property-binding surface so clients cannot submit `admin=true`, `ownerId=...`, or huge collection indices.

### 4.3. Constructor binding and pre-existing models

For immutable DTOs, Spring MVC can bind constructor parameters from request values. Example:

~~~java
public record SearchFilter(String keyword, Integer minPrice) {}
~~~

When hitting `GET /products?keyword=java&minPrice=100`, MVC can construct the record via its constructor instead of setters. Spring needs parameter names, typically from Java metadata or annotations; `@BindParam` maps request names that differ from Java names. Spring Framework 6.1+ adds `DataBinder#setDeclarativeBinding(true)` to favor constructor binding and permit setter/property binding only when allowed fields are declared.

If an object already resides in the Model or `@SessionAttributes`, Spring can bind onto that instance instead of creating a new one. To read a model attribute **without letting the request overwrite it**, use `@ModelAttribute(binding=false)`.

### 4.4. `@InitBinder` and property protection

Example controller configuring an allowed field list:

~~~java
@InitBinder("profile")
void configureBinding(WebDataBinder binder) {
    binder.setAllowedFields("name", "age", "newsletter");
}
~~~

This is a **snippet inside a controller**. `setAllowedFields` is an allowlist for **property binding**, not a business-layer authorization check. `BindingResult#getSuppressedFields()` can record blocked fields so the application can decide whether to reject or log them.

**Security principle:** never bind directly onto JPA entities containing sensitive internal fields; use request/form DTOs containing only fields clients are allowed to modify. Even with `@Valid`, always enforce authorization for update actions.

## 5. `@RequestBody` details: bodies, converters, and Content-Type

### 5.1. What does `HttpMessageConverter` read?

`org.springframework.http.converter.HttpMessageConverter<T>` defines reading/writing HTTP messages for a Java type and media type. In Spring MVC, converters are registered by configuration; common implementations include:

| Converter | Common media types | Typical target |
| --- | --- | --- |
| Jackson JSON converter (e.g., `MappingJackson2HttpMessageConverter` in Spring Framework 6.x) | `application/json`, JSON-compatible | POJOs, records, configured JSON structures. |
| `StringHttpMessageConverter` | `text/*` and supported text media types | `String`. |
| `ByteArrayHttpMessageConverter` | Various media types | `byte[]`. |
| `FormHttpMessageConverter` | `application/x-www-form-urlencoded` | `MultiValueMap<String, String>` (not arbitrary JavaBeans). |
| XML converter if configured | `application/xml`, `text/xml` | Beans/DTOs per mapping library. |

Converters provide `canRead(...)`/`read(...)` and `canWrite(...)`/`write(...)` or typed variants. Spring chooses the appropriate converter based on **argument type**, `Content-Type`, and configuration. JSON mapping follows Jackson's rules (field names, constructor/record support, custom serializers/deserializers, unknown fields...); **it does not use `ServletRequestDataBinder`'s allowed-fields list when reading JSON**.

**Special note on forms:** despite `FormHttpMessageConverter` existing, Spring MVC recommends `@RequestParam` or `@ModelAttribute` for form-urlencoded data. The Servlet API may consume the request body when reading parameters, making re-reading via `@RequestBody` unreliable; `FormHttpMessageConverter` mainly reads forms into `MultiValueMap` in appropriate contexts. Do not assume “the converter supports x-www-form-urlencoded” means `@RequestBody MyForm` deserializes forms into POJOs like Jackson reads JSON.

### 5.2. Distinguishing `Content-Type`, `consumes`, `Accept`, and `produces`

- Request header `Content-Type` describes **the body being sent**, helping Spring choose a reader converter.
- `@PostMapping(consumes = "application/json")` is a **handler matching condition**; sending another media type can trigger HTTP **415 Unsupported Media Type** before reading the body.
- Request header `Accept` states what **response type** the client wants.
- `@GetMapping(produces = "application/json")` constrains the **response representation**; if unacceptable, it can produce HTTP **406 Not Acceptable**.

Do not confuse `Content-Type` with `Accept`. An API can **accept JSON** yet **return plain text** if the method returns `String` with `@ResponseBody`.

### 5.3. JSON errors happen *before* validation

With `@Valid @RequestBody JsonProfile`:

~~~http
POST /profiles/json
Content-Type: application/json

{"name":"Lan","age":"not-a-number"}
~~~

If Jackson cannot convert that value into `Integer`, Spring reports a message-reading error, typically `HttpMessageNotReadableException` → HTTP 400 by default. If the JSON body parses cleanly yet `name=""` violates `@NotBlank` or `age=16` violates `@Min(18)`, Bean Validation then reports an error, typically `MethodArgumentNotValidException` → HTTP 400 if the controller has no local `Errors/BindingResult`.

Do not expect `WebDataBinder`'s `typeMismatch` error code for JSON parse failures. Likewise, do not try to use `try/catch` inside a controller method to catch malformed JSON syntax: the controller may not even be invoked.

## 6. Spring Boot 3.x, Java 17+ example: the same data through two pipelines

Create a **Spring Boot 3.x**, **Java 17+**, Maven project. Add these dependencies in `pom.xml` (or select Web/Validation when generating the project):

~~~xml
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
~~~

The code below has **four Java files in `src/main/java/com/example/binding/`** and one test file in `src/test/java/com/example/binding/`. There are no placeholder packages, and each `public` top-level class/record matches its filename.

### 6.1. `BindingComparisonApplication.java`

~~~java
package com.example.binding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingComparisonApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingComparisonApplication.class, args);
    }
}
~~~

### 6.2. `ProfileForm.java`: JavaBean for form/query binding

~~~java
package com.example.binding;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class ProfileForm {

    @NotBlank
    private String name;

    @NotNull
    @Min(18)
    private Integer age;

    private boolean newsletter;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }

    public boolean isNewsletter() {
        return newsletter;
    }

    public void setNewsletter(boolean newsletter) {
        this.newsletter = newsletter;
    }
}
~~~

`ProfileForm` has a default no-arg constructor and getters/setters for the binder to write data. `Integer` is used instead of `int` so `@NotNull` can detect missing `age`; `@Min(18)` verifies minimum age.

### 6.3. `ProfileJson.java`: record for JSON bodies

~~~java
package com.example.binding;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record ProfileJson(
        @NotBlank String name,
        @NotNull @Min(18) Integer age,
        boolean newsletter) {
}
~~~

Jackson reads JSON properties and instantiates the record; there are no setters. `@Valid` on the controller triggers validation after deserialization succeeds. Records do not automatically prevent all over-posting risks if they contain server-only fields, so declare only allowed inputs.

### 6.4. `ProfileController.java`

~~~java
package com.example.binding;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/profiles")
public class ProfileController {

    // Allow only properties defined in the form contract.
    @InitBinder("profile")
    void configureFormBinder(WebDataBinder binder) {
        binder.setAllowedFields("name", "age", "newsletter");
    }

    // GET query string → @ModelAttribute (@Valid omitted in GET demo).
    @GetMapping("/query")
    public String query(
            @ModelAttribute("profile") ProfileForm profile) {
        return "QUERY:" + profile.getName() + ":"
                + profile.getAge();
    }

    // Form-urlencoded → WebDataBinder/JavaBean properties.
    @PostMapping(path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<String> form(
            @Valid @ModelAttribute("profile") ProfileForm profile,
            BindingResult result) {

        if (result.hasErrors()
                || result.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest().body("FORM_INVALID");
        }

        return ResponseEntity.ok(
                "FORM:" + profile.getName() + ":"
                + profile.getAge() + ":"
                + profile.isNewsletter());
    }

    // JSON body → HttpMessageConverter (typically Jackson).
    @PostMapping(path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public String json(@Valid @RequestBody ProfileJson profile) {
        return "JSON:" + profile.name() + ":"
                + profile.age() + ":"
                + profile.newsletter();
    }

    // Syntactically valid JSON that violates Bean Validation:
    // handle errors inline via BindingResult right after @RequestBody.
    @PostMapping(path = "/json-checked",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> jsonChecked(
            @Valid @RequestBody ProfileJson profile,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body("JSON_INVALID");
        }

        return ResponseEntity.ok("JSON_OK");
    }
}
~~~

**Notable points in the controller:**

- `@RestController` causes returned `String`s to be written to the **HTTP response body**, rather than treated as view names. This is the **write** direction via converters.
- `@InitBinder("profile")` configures the binder for model attribute `profile`, setting an allowlist for **property binding**. It does **not** govern Jackson deserializing `ProfileJson`.
- `@Valid` is the validation step, distinct from binding/deserialization. `BindingResult` sits **immediately after** the validated parameter so Spring can pass errors to the controller.
- If a client sends `admin=true` in the form, the binder suppresses it because it is not in allowed fields; the controller explicitly rejects requests with suppressed fields.
- `/json` has no `BindingResult`, so Bean Validation errors are converted to HTTP 400 by the framework by default. `/json-checked` handles those same errors **in controller code** once the body has successfully converted into an object.

### 6.5. `BindingComparisonApplicationTest.java`: MockMvc end-to-end MVC tests

Create `src/test/java/com/example/binding/BindingComparisonApplicationTest.java`:

~~~java
package com.example.binding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BindingComparisonApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void queryParametersUseModelAttribute() throws Exception {
        mvc.perform(get("/profiles/query")
                    .param("name", "Hoa")
                    .param("age", "30"))
                .andExpect(status().isOk())
                .andExpect(content().string("QUERY:Hoa:30"));
    }

    @Test
    void formFieldsUseWebDataBinder() throws Exception {
        mvc.perform(post("/profiles/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("name", "Lan")
                    .param("age", "26")
                    .param("newsletter", "true"))
                .andExpect(status().isOk())
                .andExpect(content().string("FORM:Lan:26:true"));
    }

    @Test
    void badFormNumberIsBindingError() throws Exception {
        mvc.perform(post("/profiles/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("name", "Lan")
                    .param("age", "not-a-number"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("FORM_INVALID"));
    }

    @Test
    void extraFormPropertyIsSuppressedByAllowlist()
            throws Exception {
        mvc.perform(post("/profiles/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("name", "Lan")
                    .param("age", "26")
                    .param("admin", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("FORM_INVALID"));
    }

    @Test
    void jsonBodyUsesMessageConverter() throws Exception {
        mvc.perform(post("/profiles/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"Minh","age":25,"newsletter":true}
                            """))
                .andExpect(status().isOk())
                .andExpect(content().string("JSON:Minh:25:true"));
    }

    @Test
    void validJsonSyntaxButInvalidFieldsProduces400()
            throws Exception {
        mvc.perform(post("/profiles/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"","age":16,"newsletter":false}
                            """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void localBindingResultCanHandleJsonValidation()
            throws Exception {
        mvc.perform(post("/profiles/json-checked")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"","age":16,"newsletter":false}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("JSON_INVALID"));
    }

    @Test
    void malformedJsonFailsBeforeControllerValidation()
            throws Exception {
        mvc.perform(post("/profiles/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"name\":"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void wrongMediaTypeDoesNotMatchJsonMapping()
            throws Exception {
        mvc.perform(post("/profiles/json")
                    .contentType(MediaType.TEXT_PLAIN)
                    .content("name=Lan&age=26"))
                .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void missingRequiredRequestBodyProduces400()
            throws Exception {
        mvc.perform(post("/profiles/json")
                    .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest());
    }
}
~~~

Run tests from the Maven project root:

~~~bash
./mvnw test -Dtest=BindingComparisonApplicationTest
~~~

On Windows use `mvnw.cmd test -Dtest=BindingComparisonApplicationTest`, or `mvn test -Dtest=BindingComparisonApplicationTest` if Maven is installed globally.

**Expected result:** **10 passing tests** in a standard Boot 3.x Web + Validation + Test project. Below are the **expected HTTP response bodies/statuses**, not the full Maven log:

| Request/test | HTTP status | Key body |
| --- | --- | --- |
| GET `/profiles/query?name=Hoa&age=30` | 200 | `QUERY:Hoa:30` |
| POST form `name=Lan&age=26&newsletter=true` | 200 | `FORM:Lan:26:true` |
| POST form `age=not-a-number` | 400 | `FORM_INVALID` |
| POST form with `admin=true` | 400 | `FORM_INVALID` |
| POST valid JSON `{"name":"Minh","age":25,...}` | 200 | `JSON:Minh:25:true` |
| POST JSON invalid fields `name=""`, `age=16` | 400 | Framework error response (format may vary by Spring Boot). |
| POST JSON invalid fields at `/json-checked` | 400 | `JSON_INVALID` |
| POST malformed JSON | 400 | Framework error response. |
| POST `text/plain` body to JSON-only endpoint | 415 | Framework error response. |
| POST JSON with empty body when `required=true` | 400 | Framework error response. |

Note that **default error response bodies** depend on error-handling configuration, Spring version, and `@ControllerAdvice`. Tests therefore assert status codes for framework-handled errors and exact bodies only for controller-generated responses. If Spring Security is enabled, CSRF/authentication can alter POST outcomes and requires matching test setup; this demo uses only the starters listed above.

### Testing with curl

While the app is running with `./mvnw spring-boot:run`:

~~~bash
curl -i "http://localhost:8080/profiles/query?name=Hoa&age=30"

curl -i -X POST "http://localhost:8080/profiles/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "name=Lan&age=26&newsletter=true"

curl -i -X POST "http://localhost:8080/profiles/json" \
  -H "Content-Type: application/json" \
  -d '{"name":"Minh","age":25,"newsletter":true}'
~~~

These are Unix shell examples. On Windows PowerShell, use `curl.exe` for genuine curl syntax; quoting and line-continuation rules may differ. Expected outputs are `QUERY:Hoa:30`, `FORM:Lan:26:true`, and `JSON:Minh:25:true` with HTTP 200 respectively.

## 7. Validation and HTTP errors: two paths to distinguish

### 7.1. Binding errors vs JSON parse errors

| Scenario | Stage where error occurs | Typical exception/result |
| --- | --- | --- |
| `@ModelAttribute` with `age=abc` | Spring conversion during binding | `BindingResult` has `FieldError` with code `typeMismatch`; if unhandled, MVC may throw `MethodArgumentNotValidException`. |
| `@ModelAttribute` with `age=16` and `@Min(18)` | Bean Validation after binding | Field error in `BindingResult` or MVC returns HTTP 400. |
| `@RequestBody` with broken JSON `{"name":` | Converter/Jackson before deserialization finishes | `HttpMessageNotReadableException`, typically HTTP 400. |
| `@RequestBody` with valid JSON but `name=""` | Bean Validation after deserialization | `MethodArgumentNotValidException`, typically HTTP 400 if no `BindingResult` immediately follows. |
| JSON endpoint receives `Content-Type: text/plain` | Mapping selection or converter lookup | Typically HTTP 415; `consumes` may reject before converter step. |
| `@RequestBody(required=true)` with empty body | Reading required body | Typically HTTP 400; with `required=false`, handle `null` explicitly. |
| Method has direct constraints on another argument | Spring MVC method validation | May be `HandlerMethodValidationException` depending on signature and version. |

To inspect errors locally:

~~~java
@PostMapping("/form")
String handle(@Valid @ModelAttribute("profile") ProfileForm form,
              BindingResult result) {
    if (result.hasErrors()) {
        for (var error : result.getFieldErrors()) {
            System.out.println(
                    error.getField() + ": " + error.getCode());
        }
        return "profile-form";
    }
    return "success";
}
~~~

This snippet is for a **controller returning a view name**, not a replacement method inside section 6's `@RestController`. `BindingResult` must immediately follow the corresponding `@ModelAttribute`. With `@RequestBody`, `Errors/BindingResult` can immediately follow it to handle **validation errors** once the body deserializes; do not expect it to catch JSON syntax errors.

### 7.2. `@Valid`, `@Validated`, and method validation errors

- `@Valid` on an input bean instructs Bean Validation to check constraint annotations inside the DTO. `@Validated` can also select validation groups.
- For an independently validated argument lacking a matching `BindingResult`, failures typically become `MethodArgumentNotValidException`.
- If a method places constraints directly on parameters or its return value, Spring MVC (especially from Spring Framework 6.1) can switch to **method validation**, where the exception may be `HandlerMethodValidationException`.
- Before returning error messages to clients, convert them into a stable structured response in `@ControllerAdvice` or a dedicated handler; never expose stack traces.

**Do not** assume “adding `@Valid` automatically turns every error into HTTP 400” in every application: custom exception handlers, security, method validation, and MVC configuration can affect status codes. The rules above describe standard behavior under default Spring Boot MVC configuration.

## 8. Multipart, `@RequestParam`, `@RequestPart`, and a common misconception

File upload form case:

~~~http
POST /profiles/photo
Content-Type: multipart/form-data; boundary=...

--...
Content-Disposition: form-data; name="name"

Lan
--...
Content-Disposition: form-data; name="avatar"; filename="a.png"
Content-Type: image/png

...file bytes...
--...--
~~~

For form/multipart payloads, `@ModelAttribute` on a form object with a `MultipartFile avatar` property or `@RequestParam("avatar") MultipartFile file` is common. When a multipart request includes a **JSON part** marked `Content-Type: application/json`, `@RequestPart` lets a message converter deserialize that part individually:

~~~java
@PostMapping(path = "/photos",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public String upload(@Valid @RequestPart("metadata") PhotoMetadata meta,
                     @RequestPart("avatar") MultipartFile avatar) {
    // Parts can be processed differently.
    return "ok";
}
~~~

This is a **separate snippet**; it requires a `PhotoMetadata` class, imports, and safe upload handling. `@RequestPart` can use `HttpMessageConverter` for the metadata part, whereas `@ModelAttribute` binds form fields. **Do not confuse `@RequestBody JsonProfile` with automatically merging all multipart parts into one JSON object.**

In simpler APIs, `@RequestParam String name` reads **a single** request parameter value, while `@ModelAttribute ProfileForm form` binds **multiple values** into an object. Use `@RequestHeader`/`@CookieValue` explicitly for headers/cookies when needed instead of mixing them uncontrollably into a DTO.

## 9. Security: preventing over-posting in both pipelines

Whether through a form binder or a JSON converter, client data is **untrusted**. The same `admin=true` payload is dangerous if a controller binds directly onto an entity that allows updating that property.

### 9.1. With `@ModelAttribute`

- Prefer **form/request DTOs** containing only accepted fields. If using setter/property binding, configure an `setAllowedFields(...)` allowlist.
- Consider immutable constructor binding/`setDeclarativeBinding(true)` if your Spring version supports it.
- For nested properties, allow only intentional paths; avoid overly broad wildcards across entity graphs.
- Inspect `getSuppressedFields()` when you want to reject requests attempting to bind blocked fields.
- Do not confuse `@Valid` with authorization: validation checks **values**, not **permission to modify a property**.

### 9.2. With `@RequestBody`

- **Never apply `WebDataBinder#setAllowedFields` as a JSON field allowlist**; converters follow their own deserialization rules.
- Use request DTOs/records containing only allowed input fields. Configure mapper/annotations like `@JsonProperty` and `@JsonIgnore` where appropriate, without treating annotations as a substitute for authorization.
- Never pass a raw JSON request entity straight into JPA `save`. On updates, manually map permitted fields onto the entity after verifying permissions and values.
- Distinguish missing fields, nulls, unknown JSON properties, and validation rules. Jackson can be configured to handle unknown fields in several ways; **do not assume unknown fields are automatically rejected** without testing.
- Enforce body size limits, payload depth limits, and DoS protections at the web/server/gateway layer.

**Consistent rule:** define a narrow input contract, run validation, then enforce authorization in the business layer. Regardless of annotation, server-only fields (such as `role`, `ownerId`, `balance`) must be controlled solely by the server.

## 10. Quick FAQ and common errors

### “Sending JSON, yet `@ModelAttribute` receives an empty object?”

Because `@ModelAttribute` reads request values via the binder (query/form), **it does not automatically invoke Jackson to parse a raw JSON body**. Use `@RequestBody` with `Content-Type: application/json` to deserialize JSON. If an endpoint needs both query params and a body, declare separate parameters, such as `@RequestParam String source` and `@RequestBody JsonProfile payload`.

### “Can `@RequestBody` be used for form-urlencoded?”

Some converters support reading `application/x-www-form-urlencoded` into `MultiValueMap<String,String>`. However, in Servlet MVC, accessing request parameters can consume the form body and prevent `@RequestBody` from reading it reliably. Spring recommends **`@RequestParam`/`@ModelAttribute` for forms**; do not expect `@RequestBody MyPojo` to parse HTML forms like JSON by default.

### “Why does `@RequestBody` return 400 while `@ModelAttribute` produces a `FieldError`?”

A JSON body must be deserialized by a converter into an object before `@Valid` runs. If syntax is broken, the converter fails → `HttpMessageNotReadableException`. With forms, the binder records `typeMismatch` in `BindingResult`. Without a local handler, Spring MVC still turns binding/validation errors into HTTP 400.

### “Must `@ModelAttribute` be written explicitly on every parameter?”

In Spring MVC, a complex parameter not claimed by another resolver can be treated as an **implicit `@ModelAttribute`**. However, writing it **explicitly** improves readability, clarifies the API contract, and provides better AOT/native-image hints. Never treat omitting the annotation as a way to disable binding.

### “Can `@ModelAttribute` be used at the method level?”

Yes, with a **different meaning**: a `@ModelAttribute` method in `@Controller`/`@ControllerAdvice` typically **populates Model values** before handlers run, whereas `@ModelAttribute` on a **handler parameter** retrieves/binds a model object. Do not confuse the two roles.

### “Are all JSON errors `@Valid` errors?”

No. JSON can fail on syntax, missing body, type mismatch, or converter errors before Bean Validation ever runs. Inspect **which stage failed** and the exception type; do not lump every HTTP reading failure under “constraint violation”.

### “Why does `@ResponseBody` appear alongside this topic?”

Because `HttpMessageConverter` works in **two directions**: `@RequestBody` reads the body into a Java object; `@ResponseBody` writes a Java object/String to the HTTP response. `@RestController` includes `@ResponseBody`. It is an easy pair to remember, without turning `@ModelAttribute` into a converter.

## 11. Quick selection checklist

| Data sent by client | Annotation to consider | Notes |
| --- | --- | --- |
| `GET /search?keyword=java&size=10` | `@RequestParam` for a few fields; `@ModelAttribute` for a filter DTO. | No JSON parser needed. |
| HTML `application/x-www-form-urlencoded` | `@ModelAttribute` or `@RequestParam`. | Use form DTO, `BindingResult`, and allowlist. |
| REST `application/json` | `@RequestBody`. | JSON converter + `@Valid`, request DTO. |
| Plain text body | `@RequestBody String`. | `StringHttpMessageConverter` if media type matches. |
| Raw bytes body | `@RequestBody byte[]`. | Enforce size limits. |
| Multipart form upload | `@ModelAttribute`/`@RequestParam MultipartFile`. | Binds form fields + file parts. |
| Multipart with separate JSON metadata and file | `@RequestPart`. | Converter reads the JSON **part** per the part's `Content-Type`. |
| Need both query param and JSON body | `@RequestParam` + `@RequestBody` as two parameters. | Each source keeps its own contract. |

**One-sentence summary:** **`@ModelAttribute` = model + request parameter/property binding; `@RequestBody` = message body + `HttpMessageConverter`**. After data conversion, both can be validated with `@Valid`, yet their input sources, mapping mechanics, conversion errors, and field-protection strategies **differ**.

## References

- Spring Framework — `@ModelAttribute` in controllers, request parameter/URI/header sources, constructor/property binding: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework — `@RequestBody`, message conversion, validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — **HTTP Message Conversion** and converters: https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html
- Spring Framework — **MVC Data Binding** and security/model design: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework — **MVC Validation** (`MethodArgumentNotValidException`/`HandlerMethodValidationException`): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — **Multipart Forms** (`@RequestPart`): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html
