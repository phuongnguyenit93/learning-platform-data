# @RequestBody, @ModelAttribute, and Input Object Creation in Spring Boot

## 1. Goals and Context

When Spring Boot receives an HTTP request, the framework must turn external data—JSON, form fields, query parameters, URI variables, headers, or multipart parts—into Java objects for a controller to process. Two annotations that are very easy to confuse are **`@RequestBody`** and **`@ModelAttribute`**.

This lesson explains the *data reading path*, *how Java objects are created*, *how values are assigned*, *how validation works*, and *errors/security considerations* for both. The focus is Spring MVC in `spring-boot-starter-web`; the end of the lesson compares the Spring WebFlux equivalents to avoid applying the wrong runtime behavior.

After this lesson, you will be able to:
1. Choose `@RequestBody` for JSON/XML and `@ModelAttribute` for form/query binding in the right context.
2. Explain the sequence argument resolver → message converter/deserializer or binder → Java object → validation → handler.
3. Understand constructor binding, JavaBean setter binding, record/immutable DTOs, type conversion, and mismatched field names.
4. Distinguish unreadable body errors, parameter conversion errors, validation errors, and media type errors.
5. Place `BindingResult` in the right position; use `@Valid`, `@InitBinder`, and dedicated DTOs.
6. Prevent **mass assignment/over-posting** when client data controls object properties.
7. Test using curl, MockMvc, and reproducible integration tests.

Main examples: **Spring Boot 3.5.x, Spring Framework 6.2.x, Java 17+**. For other versions, verify against the API documentation for the version you are running.

## 2. Distinguishing Data Sources Before Choosing an Annotation

| Request type | Example | Typical tool choice |
|---|---|---|
| JSON body, `application/json` | `{"name":"Lan","age":24}` | `@RequestBody SignupJson` |
| URL-encoded form | `name=Lan&age=24` | `@ModelAttribute SignupForm` or `@RequestParam` |
| Query string | `GET /search?q=java&page=2` | `@RequestParam` for a few parameters; `@ModelAttribute SearchCriteria` for a group of properties |
| URL path | `GET /users/42` | `@PathVariable long id`; can participate in model-attribute binding when names match |
| Multipart form | Text parts + file | `@ModelAttribute UploadForm`, `@RequestParam MultipartFile`, or `@RequestPart` |
| Multipart JSON part | Part `metadata` with `Content-Type: application/json` | `@RequestPart("metadata") Metadata` |
| Raw bytes or text body | `text/plain`, octet-stream | `@RequestBody String`/`byte[]` when a matching converter exists |
| Standalone header or cookie | `X-Trace-Id`, `session` | `@RequestHeader`, `@CookieValue` |

Fundamental rule: `@RequestBody` represents **body content read and decoded through HTTP message conversion**, while `@ModelAttribute` represents **a model object retrieved/created and then bound with request name–value pairs**. Both mechanisms can return a Java DTO, yet their execution paths differ completely.

In Servlet MVC, URL-encoded form data is exposed by the Servlet API as request parameters; accessing those parameters can consume the body. Consequently, Spring documentation recommends using `@RequestParam` or `@ModelAttribute` for forms, **not treating `@RequestBody` as the default choice for form-urlencoded data**.

## 3. Overall Flow in Spring MVC

~~~text
HTTP request
  |
DispatcherServlet -> HandlerMapping -> HandlerAdapter
                                       |
                                       v
                            Resolver per method argument
                                       |
                    +------------------+------------------+
                    |                                     |
             @RequestBody                             @ModelAttribute
                    |                                     |
          HttpMessageConverter                       Model / Session?
                    |                                     |
       (JSON -> Jackson ObjectMapper)             existing / newly created
                    |                                     |
              JSON DTO/record                 constructor binding and/or
                    |                          property (setter) binding
                    |                                     |
                    +------------- Validation ------------+
                                       |
                         Handler method/controller
                                       |
                      Business service -> response
~~~

The controller is invoked only after the framework resolves required parameters, unless you declare `BindingResult`/`Errors` to handle supported binding/validation errors yourself. Neither mechanism **automatically saves data to a database**, and the resulting object **does not become a Spring-managed bean**.

### 3.1. The Method Argument Resolver Selects the Mechanism

Spring MVC uses `HandlerMethodArgumentResolver` implementations to inspect parameter annotations/types and produce values for the Java call. `@RequestBody` takes the `HttpMessageConverter` body-reading branch; `@ModelAttribute` takes the model attribute/binder branch. `@RequestParam`, `@PathVariable`, and `@RequestHeader` use their respective resolvers.

Because each resolver has its own contract, **do not** assume swapping `@ModelAttribute` for `@RequestBody` will keep reading form or query string data as before.

## 4. @RequestBody: Body, Message Converters, and Deserialization

Example controller accepting JSON:

~~~java
@PostMapping(path = "/users", consumes = MediaType.APPLICATION_JSON_VALUE)
ResponseEntity<UserView> create(@Valid @RequestBody CreateUserRequest request) {
    UserView created = service.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

This is a fragment assuming the DTO, service, and imports exist.

Typical workflow:
1. HandlerAdapter detects a `@RequestBody` argument.
2. HTTP `Content-Type` and the target Java type are used to select an `HttpMessageConverter`.
3. With JSON and Jackson on the classpath, `MappingJackson2HttpMessageConverter` reads the body, delegates to Jackson to instantiate the DTO, and populates fields/properties/constructor arguments.
4. If `@Valid` or `@Validated` and a validation provider are present, the framework validates object constraints.
5. The valid DTO is passed to the controller; otherwise, an exception is thrown and HTTP 400 is typically returned under default MVC configuration.

**Key point:** `@RequestBody` does not pull query string parameters to fill missing JSON fields. If a client sends `POST /users?name=Lan` with body `{"age":24}`, `name` is not automatically merged from the query into the JSON DTO. If an API needs data from both places, declare separate parameters intentionally.

### 4.1. How Does Jackson Instantiate Objects?

There is no absolute rule that every JSON DTO must have a public no-arg constructor. Depending on the object design and Jackson configuration, common patterns include:

- JavaBean: no-arg constructor + appropriate setters/field access.
- Java `record`: Jackson inspects record components and invokes the canonical constructor.
- Constructor or static factory annotated with `@JsonCreator` and `@JsonProperty` mappings where needed.
- Jackson annotations to rename fields (`@JsonProperty`) or customize deserialization rules.

Java 17 record example:

~~~java
public record CreateUserRequest(
        @NotBlank String name,
        @NotBlank @Email String email,
        @Min(18) int age) {
}
~~~

Body:

~~~json
{"name":"Lan","email":"lan@example.org","age":24}
~~~

Jackson can instantiate the record by invoking its constructor with the matching values. You do not need to add setters just to bind JSON. `@NotBlank`, `@Email`, and `@Min` are Bean Validation constraints; they are checked by the validation pipeline only when activated, such as with `@Valid` and the validation starter.

### 4.2. `required`, Empty Body, Null, and Missing Fields

`@RequestBody` defaults to `required=true`: missing a required body typically produces HTTP 400. `@RequestBody(required=false)` permits the body to be absent; the controller must handle a nullable or optional parameter accordingly.

Distinguish between:
- Empty body: no data for the message converter to build an object.
- JSON `null`: semantics depend on the converter and required checks.
- JSON object missing a field: a Java record constructor is called with null/default values if Jackson permits; **missing fields are not treated as errors by default**.
- With `int age`, omitting `age` may yield `0`, which `@Min(18)` catches when validation runs; use `Integer` + `@NotNull` if you need to distinguish "missing" from "0".
- Malformed JSON or unparseable types: typically results in HTTP 400 before the controller runs.

### 4.3. Do Not Confuse Status Codes 400, 415, and 406

| Scenario | Typical result |
|---|---|
| Required `@RequestBody` but request has no body | 400 Bad Request |
| Malformed JSON / cannot be deserialized | 400 Bad Request (`HttpMessageNotReadableException`) |
| Bean Validation on body fails | 400 by default (`MethodArgumentNotValidException`) |
| Endpoint consumes JSON only, client sends `Content-Type: text/plain` | 415 Unsupported Media Type |
| Client does not accept the response format offered | Possibly 406 Not Acceptable |
| Controller runs, but a business rule rejects syntactically valid data | Status code depends on application contract; not automatically 400/422 |

These status codes describe standard default behavior, assuming custom `@ControllerAdvice`, proxies, or libraries have not altered error mapping.

## 5. @ModelAttribute: Retrieving or Creating an Object, Then Data Binding

Example:

~~~java
@PostMapping(path = "/signup", consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
ResponseEntity<String> signup(
        @Valid @ModelAttribute("signupForm") SignupForm form) {
    return ResponseEntity.ok("Hello " + form.getName());
}
~~~

The controller receives a `SignupForm` **not via a JSON deserializer**. Spring looks up the model attribute named `signupForm` and uses `WebDataBinder` to bind matching request parameters.

A model attribute can:
- Already exist in the `Model`, e.g., prepared earlier by a method-level `@ModelAttribute`.
- Come from `@SessionAttributes` if declared on the controller and present in the session.
- Be instantiated via a default or matching primary constructor when not yet in the model.
- Be bound using constructor arguments and/or mutable bean properties depending on binder configuration.

In Spring MVC, data from **form and query parameters** can participate in binding; URI template variables and headers can also participate when names match and do not overwrite request parameters of the same name. This mechanism is powerful, which is why you must restrict which properties clients are allowed to populate.

### 5.1. JavaBean Property Binding

Typical mutable DTO:

~~~java
public class SignupForm {
    private String name;
    private int age;

    public SignupForm() {}

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public int getAge() { return age; }
    public void setAge(int age) { this.age = age; }
}
~~~

With `name=Lan&age=24`, Spring can instantiate `SignupForm` via its no-arg constructor and invoke setters. The string `"24"` is converted to `int 24` by the conversion infrastructure. You do not need to write `Integer.parseInt` in the controller for each field.

If the client sends `age=abc`, that is a **conversion/binding error**: `int` cannot accept `"abc"`, which is recorded in `BindingResult` or triggers an exception. That differs from converting successfully while `age=15` violates `@Min(18)`.

### 5.2. Constructor Binding and Immutable Objects

Spring Framework 6.x supports constructor binding for model attributes. A DTO with a primary constructor or a Java record can be constructed by mapping request parameter names to constructor arguments.

~~~java
public record SearchCriteria(String keyword, Integer page) {}
~~~

For `GET /search?keyword=java&page=2`, a `@ModelAttribute SearchCriteria criteria` parameter can be built through its constructor. Java records preserve component names; regular class constructors require Java parameter name metadata (typically via `javac -parameters`), or a name-mapping annotation such as `@BindParam` when needed.

Constructor binding and property binding **are not mutually exclusive** by default. If you want an object populated solely via its constructor for security reasons, design an immutable DTO without setters and consider configuring declarative binding appropriate for your framework version.

### 5.3. Nested Objects, Collections, Indexes, and Converters

The binder can support property paths like `address.city`, `items[0].sku`, and `tags[1]`, within configuration and object-type limits. This is convenient for complex HTML forms, but can also expose a larger data surface than intended.

When handling `LocalDate`, enums, locale-formatted numbers, or domain value objects, check `ConversionService`, `Converter`, `Formatter`, `@DateTimeFormat`, and `@NumberFormat`. Do not push ad-hoc string parsing into business services when the binder can enforce it per the API contract.

## 6. Object Structure: How Does a JSON Record Differ from a Form Bean?

| Question | `@RequestBody` | `@ModelAttribute` |
|---|---|---|
| Primary source | Request body (JSON/XML/bytes...) | Request parameter values, model/session, form/query; optionally path/header when applicable |
| Reading component | `HttpMessageConverter` (MVC) | `WebDataBinder` and model attribute resolution |
| Instantiation mechanism | Deserializer: no-arg/setter, record, `@JsonCreator`... | Existing model object, constructor binding, default constructor + property binding |
| Naming | JSON property names, Jackson annotations | Request parameter/property names, `@BindParam`, and binder configuration |
| Type conversion | JSON parsing/deserialization + Jackson types | Spring type conversion/formatters |
| Validation | `@Valid`/`@Validated` on DTO | `@Valid`/`@Validated` on model attribute |
| URL-encoded forms | Not recommended as default in MVC | Well suited |
| Nested fields | Follows JSON tree | Follows property paths like `address.city` |
| Disallowed bind data | JSON deserializer/DTO/Jackson policy | Allowed fields, DTO, constructor-only strategy |
| Common failures | Missing/invalid body, unsupported media | Type mismatch, unknown/disallowed fields, binding errors |

Both approaches use `@Valid`, but error details can differ when the body is unreadable or conversion fails. Do not write an error handler assuming every input failure produces `MethodArgumentNotValidException`.

## 7. Validation: When Does It Run and Where Does BindingResult Go?

`jakarta.validation.Valid` triggers object validation if a validation dependency is on the classpath and integrated. In Spring Boot, adding `spring-boot-starter-validation` typically provides the Jakarta Bean Validation implementation.

Constraint examples:

~~~java
record SignupJson(
        @NotBlank String name,
        @NotBlank @Email String email,
        @Min(18) int age) {}
~~~

- `@NotBlank`: rejects null, empty strings, and whitespace-only strings.
- `@Email`: checks email syntax at the constraint level; does not verify mailbox existence.
- `@Min(18)`: requires age to be at least 18; checks numeric input after conversion/deserialization.
- `@NotNull` is useful on wrappers like `Integer` when distinguishing null from zero.

### 7.1. Handling BindingResult in the Controller

With `@ModelAttribute` or `@RequestBody`, in scenarios where Spring MVC supports local error handling, the `BindingResult`/`Errors` parameter must be placed **immediately after** the validated argument:

~~~java
@PostMapping("/signup/check")
ResponseEntity<?> signup(
        @Valid @ModelAttribute("signupForm") SignupForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(Map.of("error", "Invalid signup form"));
    }
    return ResponseEntity.ok(Map.of("name", form.getName()));
}
~~~

This fragment requires `Map` and corresponding imports. Do not place `BindingResult` after another parameter and expect it to attach to `form`. Without a local error argument, validation/binding failures typically raise an exception handled by the framework or `@RestControllerAdvice`.

When constraints are placed **directly on method parameters** (not just `@Valid` on a DTO), Spring Framework can trigger method validation and throw `HandlerMethodValidationException` instead of `MethodArgumentNotValidException`. A shared error handler should account for both branches, especially when controller signatures evolve.

### 7.2. @Valid Does Not Automatically Prevent Mass Assignment

Validation only checks the values that were bound; it does not restrict which fields a client is permitted to modify. `@Valid` also does not replace authorization, resource ownership checks, business code validation, or duplicate detection.

## 8. Runnable Maven Example: One Business Operation, Two Object-Creation Paths

The example below uses `spring-boot-starter-web` (Spring MVC + default Tomcat), Java 17, and Bean Validation. It exposes three endpoints:
- `POST /api/signup/json`: reads JSON via `@RequestBody` into a record.
- `POST /api/signup/form`: reads URL-encoded form data via `@ModelAttribute` into a mutable JavaBean.
- `POST /api/signup/immutable`: reads form data into a record via constructor binding.

### 8.1. Create pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>input-binding-demo</artifactId>
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
~~~

Do not add `spring-boot-starter-webflux` for this example: the goal is to demonstrate Servlet MVC.

### 8.2. Complete Java File

Create `src/main/java/example/input/InputBindingApplication.java`:

~~~java
package example.input;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class InputBindingApplication {
    public static void main(String[] args) {
        SpringApplication.run(InputBindingApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/signup")
class SignupController {

    @PostMapping(path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<SignupView> json(
            @Valid @RequestBody SignupJson input) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new SignupView(
                        "json", input.name(), input.email(), input.age()));
    }

    @PostMapping(path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    ResponseEntity<SignupView> form(
            @Valid @ModelAttribute("signupForm") SignupForm input) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new SignupView(
                        "form", input.getName(), input.getEmail(), input.getAge()));
    }

    @PostMapping(path = "/immutable",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    ResponseEntity<SignupView> immutable(
            @Valid @ModelAttribute SignupRecord input) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new SignupView(
                        "record", input.name(), input.email(), input.age()));
    }

    @InitBinder("signupForm")
    void limitSignupFields(WebDataBinder binder) {
        binder.setAllowedFields("name", "email", "age");
    }
}

record SignupJson(
        @NotBlank String name,
        @NotBlank @Email String email,
        @Min(18) int age) {}

record SignupRecord(
        @NotBlank String name,
        @NotBlank @Email String email,
        @Min(18) int age) {}

record SignupView(String source, String name, String email, int age) {}

class SignupForm {

    @NotBlank
    private String name;

    @NotBlank
    @Email
    private String email;

    @Min(18)
    private int age;

    public SignupForm() {}

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public int getAge() { return age; }
    public void setAge(int age) { this.age = age; }
}
~~~

This is a valid Java source file with **one public class** matching the file name, while the remaining types are package-private. The Spring Boot parent configures compilation for the Java version specified above, compatible with records and constructor parameter names. The controller does not persist data; it echoes the bound values for easy inspection. In production, map DTOs into domain/service calls per business logic.

`@InitBinder("signupForm")` restricts allowed fields for the model attribute named `signupForm`. This demonstrates controlling **property binding** on a mutable form endpoint, not a reason to bind sensitive entities directly; constructor binding is controlled via the constructor parameters of a dedicated DTO.

### 8.3. Running and Testing Each Endpoint

In the directory containing `pom.xml`, with Java 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -i -X POST http://localhost:8080/api/signup/json \
  -H "Content-Type: application/json" \
  -d '{"name":"Lan","email":"lan@example.org","age":24}'
~~~

Expected key result: **HTTP 201** and JSON:

~~~json
{"source":"json","name":"Lan","email":"lan@example.org","age":24}
~~~

Send a URL-encoded form:

~~~bash
curl -i -X POST http://localhost:8080/api/signup/form \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=Minh" \
  --data-urlencode "email=minh@example.org" \
  --data-urlencode "age=21"
~~~

Expected key result: **HTTP 201**, JSON:

~~~json
{"source":"form","name":"Minh","email":"minh@example.org","age":21}
~~~

Send the same form format into an immutable record:

~~~bash
curl -i -X POST http://localhost:8080/api/signup/immutable \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=An" \
  --data-urlencode "email=an@example.org" \
  --data-urlencode "age=30"
~~~

Expected key result: **HTTP 201** and JSON:

~~~json
{"source":"record","name":"An","email":"an@example.org","age":30}
~~~

Other headers, ports, charsets, and response property ordering depend on runtime configuration. The JSON snippets represent expected data; JSON clients should not rely on key order.

### 8.4. Testing Validation and Content-Type Errors

~~~bash
# Age violates constraint
curl -i -X POST http://localhost:8080/api/signup/json \
  -H "Content-Type: application/json" \
  -d '{"name":"Lan","email":"lan@example.org","age":15}'

# Invalid age format: binder cannot convert "abc" to int
curl -i -X POST http://localhost:8080/api/signup/form \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "name=Minh&email=minh@example.org&age=abc"

# Wrong media type sent to JSON endpoint
curl -i -X POST http://localhost:8080/api/signup/json \
  -H "Content-Type: text/plain" \
  -d "name=Lan"
~~~

The three expected statuses are typically **400**, **400**, and **415** in default MVC. Error bodies can vary by version, `server.error.*`, and custom exception handlers, so do not hardcode an error JSON shape unless you have designed a custom error contract.

## 9. Unit/Integration Tests for Object Creation Mechanisms

With `spring-boot-starter-test` from the example, create `src/test/java/example/input/InputBindingApplicationTests.java`:

~~~java
package example.input;

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
class InputBindingApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsJsonViaRequestBody() throws Exception {
        mvc.perform(post("/api/signup/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"Lan","email":"lan@example.org","age":24}
                    """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.source").value("json"))
                .andExpect(jsonPath("$.age").value(24));
    }

    @Test
    void bindsFormParametersViaModelAttribute() throws Exception {
        mvc.perform(post("/api/signup/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("name", "Minh")
                .param("email", "minh@example.org")
                .param("age", "21"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.source").value("form"))
                .andExpect(jsonPath("$.name").value("Minh"));
    }

    @Test
    void rejectsInvalidJson() throws Exception {
        mvc.perform(post("/api/signup/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"","email":"invalid","age":15}
                    """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsFormTypeMismatch() throws Exception {
        mvc.perform(post("/api/signup/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("name", "Minh")
                .param("email", "minh@example.org")
                .param("age", "abc"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The tests are expected to **PASS** on the described project, since JSON is read through the message converter, form parameters through the binder, Bean Validation is active, and binding/validation errors are mapped to 400 by Spring MVC. MockMvc tests do not replace servlet-container integration tests when you need to verify upload limits, multipart streaming, or proxy infrastructure, but they are well suited to verifying argument binding.

## 10. @ModelAttribute Also Has Method-Level Semantics

The `@ModelAttribute` annotation serves multiple roles:

1. **On a method parameter:** retrieves or creates a model object and binds request data.
2. **On a controller or `@ControllerAdvice` method:** populates data into the `Model` before the request handler executes.
3. **On a handler return value:** explicitly marks the returned data as a model attribute in view-rendering controllers.

Example fragment:

~~~java
@ModelAttribute("countries")
List<String> countries() {
    return List.of("VN", "SG", "JP");
}

@GetMapping("/signup-page")
String page(Model model) {
    model.addAttribute("form", new SignupForm());
    return "signup-page";
}
~~~

This example requires imports and a matching template engine/view; it is not an endpoint in the REST demo in Section 8. The `countries()` method populates model data; it is **not** a request body decoder.

Using `@ModelAttribute(binding=false)` accesses an existing model attribute without performing data binding on it. This is appropriate when you have already loaded a domain object securely and do not want the client to overwrite its properties.

## 11. Multipart: Do Not Confuse Form Fields, Files, and JSON Parts

HTML upload forms typically send `multipart/form-data`. A DTO for binding might contain:
- `String title`;
- `MultipartFile file` (Servlet MVC);
- other text fields with suitable setter/constructor binding.

Illustrative controller fragment:

~~~java
@PostMapping(path = "/documents", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
ResponseEntity<?> upload(@Valid @ModelAttribute UploadForm form) {
    if (form.getFile() == null || form.getFile().isEmpty()) {
        return ResponseEntity.badRequest().body("file is required");
    }
    return ResponseEntity.ok(Map.of(
            "title", form.getTitle(),
            "size", form.getFile().getSize()));
}
~~~

This requires an `UploadForm` class with `title`, `MultipartFile file`, getters/setters, and imports; it is **not** part of the standalone main demo. When a part contains JSON with its own Content-Type, using `@RequestPart("metadata") @Valid Metadata metadata` and `@RequestPart("file") MultipartFile file` expresses the contract more clearly.

Never call `getBytes()` on huge files just to check metadata; enforce upload size limits, file types, safe path handling, and authorization before saving. In Servlet MVC, `spring.servlet.multipart.*` controls Spring Boot's upload limits within supported configuration boundaries.

## 12. Security: Mass Assignment, DTOs, and Allowed Fields

This is the single most important security risk of model attribute binding. Suppose a domain entity has:
- `displayName` — editable by the user.
- `email` — editable through a verification workflow.
- `role` — changeable only by admins.
- `balance` — computed by the system.
- `ownerId` — must come from the authenticated identity.

If a controller binds a mutable domain entity directly with `@ModelAttribute`, an attacker can submit extra fields such as `role=ADMIN`, `balance=999999`, or `ownerId=...`. If the binder allows setting those fields and the service saves the entity, that is **mass assignment/over-posting**. Never assume a client cannot submit a field merely because the UI hides it.

Priority mitigations:
1. **Design dedicated request DTOs** containing only editable fields.
2. Consider constructor binding with immutable DTOs/records where appropriate.
3. With property binding, restrict `allowedFields` via `@InitBinder` or equivalent binder configuration.
4. Never bind sensitive JPA entities directly, especially objects loaded from the database by ID and placed in the model.
5. Enforce authorization and business checks in the service layer. `allowedFields` does not verify who is permitted to modify a resource.
6. Apply similar discipline to JSON `@RequestBody`: dedicated request DTOs, Jackson binding policies, and explicit mapping to entities; JSON is not immune to over-posting by default.

Intentional fragment:

~~~java
@InitBinder("accountForm")
void accountBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
}
~~~

This restricts **property binding** for the `accountForm` model attribute. Constructor binding must be controlled via the constructor/DTO design itself; do not treat `setAllowedFields` as a universal blocklist across every input source and stage.

## 13. Type Conversion, Errors, and Response Status Choices

| Issue | What to investigate | Typical result and handling |
|---|---|---|
| `@RequestBody` is null/missing | Empty body, violated required contract | 400 or handle nullable/optional if intentional |
| `HttpMessageNotReadableException` | Malformed JSON, type cannot be deserialized | 400; do not call business service |
| `HttpMediaTypeNotSupportedException` | Content-Type does not match `consumes`/available converters | 415; verify client sends the expected media type |
| `MethodArgumentNotValidException` | Bean Validation or binding errors on object | 400 by default; return consistent error details |
| `HandlerMethodValidationException` | Method-level constraints on parameters/return values | Status depends on validation direction; typically 400 for request inputs |
| `BindException`/field binding errors | Form parameter cannot be converted or is missing | Check BindingResult, field errors; typically 400 |
| Form `age=abc` | Converter cannot turn string into int | 400, identify field `age` |
| JSON `age="abc"` | Jackson cannot deserialize int from invalid string | 400 before a valid DTO is instantiated |
| Unknown JSON properties | Jackson policy on unknown fields | May be ignored or rejected; inspect ObjectMapper config |
| Over-posting | DTO exposes sensitive fields or binds an entity | Fix model design/allowedFields/authorization |

**Never return raw exception stack traces or the full raw request body to clients.** Standardize error responses with `@RestControllerAdvice` where needed, while distinguishing field validation, parser errors, and media type errors. JSON Problem Details (`ProblemDetail`) is one option when an API standardizes on it, though not the only choice.

### 13.1. Which Error Status Should an API Return?

- Malformed syntax or unbindable request: typically **400 Bad Request**.
- Unsupported media type: **415 Unsupported Media Type**.
- Syntactically valid content violating a business rule: depends on contract—often **400**, **409**, or **422**; do not assume 422 is returned automatically by `@Valid`.
- Missing authentication or permission: **401/403**, handled at the appropriate security layer.

Returning clean error responses does not replace testing that **the service persisted no data** when binding or validation failed.

## 14. @RequestBody and @ModelAttribute in Spring WebFlux

WebFlux uses the same two annotations, but its **infrastructure differs from MVC**:

| Component | Spring MVC | Spring WebFlux |
|---|---|---|
| HTTP server | Servlet container | Reactive runtime, typically Reactor Netty |
| Reading `@RequestBody` | `HttpMessageConverter` | `HttpMessageReader` / codecs |
| Reactive body wrapper arguments | Not used like WebFlux for non-blocking reads | Supports `Mono<T>` and reactive types per contract |
| `@ModelAttribute` | `WebDataBinder` for form/query/model objects | Reactive-aware binder; form/query and supported sources |
| `@RequestBody` validation | Typically `MethodArgumentNotValidException` | Typically `WebExchangeBindException` |
| Waiting to read body | Follows Servlet/I/O runtime | Never call `block()` in reactive handlers |

Example **fragment in a WebFlux application**—do not paste into the Spring MVC project in Section 8 expecting it to run as-is:

~~~java
@PostMapping(path = "/users", consumes = MediaType.APPLICATION_JSON_VALUE)
Mono<ResponseEntity<UserView>> create(
        @Valid @RequestBody Mono<CreateUserRequest> requestMono) {

    return requestMono.map(input ->
            ResponseEntity.status(HttpStatus.CREATED)
                    .body(new UserView(input.name(), input.email())));
}
~~~

Here `CreateUserRequest` and `UserView` are records/classes from a separate project; the method illustrates reading and validating a body via a reactive publisher. Never call `requestMono.block()`. When using `BindingResult` with WebFlux, note that reactive wrapper arguments do not use a local `BindingResult` parameter in the same way synchronous object arguments do; errors are typically handled via `onErrorResume` or a WebFlux error handler.

With `@ModelAttribute`, WebFlux can also bind form/query/path/header values into an object, but non-blocking form reading and request lifecycle differ from Servlet. Never use `HttpServletRequest.getParameterMap()` in Netty WebFlux.

## 15. Common Mistakes

1. **Using `@RequestBody` for every URL-encoded form in MVC:** risks Servlet parameter parsing conflicts; use `@ModelAttribute`/`@RequestParam`.
2. **Assuming `@ModelAttribute` reads an entire JSON body:** wrong mechanism; JSON needs a body converter with `@RequestBody`.
3. **Assuming `@RequestBody` automatically merges query params into a JSON DTO:** incorrect.
4. **Assuming `@ModelAttribute` requires a no-arg constructor:** Spring supports constructor binding and records when version/metadata requirements are met.
5. **Assuming Jackson requires public setters:** Java records and creators can deserialize without setters.
6. **Omitting a validation provider while trusting `@Valid` will always run:** missing the starter/provider can mean Bean Validation is never executed.
7. **Placing `BindingResult` away from its target argument:** Spring will not associate the error argument properly.
8. **Using a domain/JPA entity directly as `@ModelAttribute`:** creates over-posting, nested property injection, and authorization risks.
9. **Assuming validation equals authorization:** they are separate responsibilities.
10. **Assuming every invalid input returns 400:** a wrong media type may return 415; business errors have their own statuses.
11. **Confusing method-level `@ModelAttribute` with argument-level `@ModelAttribute`:** one prepares the model, the other binds a parameter.
12. **Testing JSON endpoints using `.param()` without a JSON body:** does not test `@RequestBody` deserialization.
13. **Testing form endpoints with JSON content while expecting the data binder to use params:** use the right Content-Type and request format.
14. **Sending both JSON and form expectations in the same request to trigger both argument readers:** leads to body-consumption and contract inconsistencies.
15. **Accepting `@RequestBody(required=false)` without handling null:** causes the service to throw NPE.
16. **Assuming `@Email` verifies the email address exists:** the constraint only checks format.
17. **Using `int` for a field that needs to distinguish missing/null:** the primitive default can hide missing data.
18. **Copying Servlet MVC snippets into WebFlux unmodified:** message codecs, validation exceptions, and reactive wrappers differ.

## 16. Checklist Before Merging a New Endpoint

- [ ] Determined whether the client sends JSON, URL-encoded form, query string, or multipart data.
- [ ] Used `@RequestBody` for converter/codec-supported bodies and `@ModelAttribute` for appropriate form/query data.
- [ ] Separated input DTOs from entities and response DTOs.
- [ ] Verified which constructor/setter/record/creator actually instantiates the object.
- [ ] Checked JSON property names and request parameter names, especially casing/kebab-case/indexed fields.
- [ ] Tested type conversion and malformed field handling.
- [ ] Enabled `spring-boot-starter-validation` and placed constraints/`@Valid` in the right spots.
- [ ] If using `BindingResult`, placed it immediately after the validated argument.
- [ ] Tested empty bodies, missing fields, nullable types, and primitive defaults.
- [ ] Defined an error contract that does not leak exception internals or sensitive data.
- [ ] Restricted writable fields, used dedicated DTOs, and enforced proper authorization.
- [ ] Tested JSON/form/multipart with matching `Content-Type`, covering both success and failure cases.
- [ ] If running WebFlux, verified reactive codecs, error types, and no `block()` calls.
- [ ] Added MockMvc/WebTestClient or integration tests to guard against regressions.

## 17. Conclusion

**`@RequestBody` and `@ModelAttribute` are two distinct paths for constructing input data for the same handler.** In Spring MVC, `@RequestBody` reads the HTTP body through a message converter and uses a deserializer like Jackson to instantiate a DTO; `@ModelAttribute` retrieves or instantiates a model object and uses a data binder to assign matching form/query/path/header values. Both support validation, but parse/binding failures and field-restriction capabilities differ. Choose the annotation matching the data contract, design dedicated input DTOs, verify instantiation and binding with real tests, and prevent mass assignment before data reaches your service layer.

## Official References

- Spring Framework — MVC @RequestBody: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — MVC @ModelAttribute: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework — MVC Data Binding: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework — MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — WebFlux @RequestBody: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework — WebFlux @ModelAttribute: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/modelattrib-method-args.html
- Spring Boot — Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
