# @ModelAttribute and Binding Data to Input Objects in Spring WebFlux

## 1. What is @ModelAttribute used for?

In Spring WebFlux, the `@ModelAttribute` annotation is used to **get or create a model object, then bind HTTP request data to that object's properties** through `WebDataBinder`. This object is commonly called a *model attribute*, a *command object*, or a *form-backing object*.

A method argument can declare:

~~~java
@PostMapping("/profiles")
public ProfileView update(@ModelAttribute ProfileForm form) {
    return new ProfileView(form.getDisplayName(), form.getEmail());
}
~~~

This is an illustrative snippet; `ProfileForm` and `ProfileView` need to be defined in the application. When the controller is invoked, Spring looks for a suitable attribute in the model or creates a new object, then binds the request data to it before passing it to the method.

In WebFlux, `@ModelAttribute` commonly binds these sources:

- **Query parameters**: for example `?page=2&keyword=spring`.
- **Form data**: data sent as `application/x-www-form-urlencoded`.
- **URI path variables**: for example `/accounts/42` can supply a value for a property with the same name.
- **Request headers**: header names are converted to property names according to Spring's rules.

Form data and query parameters take precedence over path variables and headers when they share a property name. Data is converted from strings to the appropriate Java types through Spring's conversion/formatting system.

**Key point:** `@ModelAttribute` is a mechanism for binding request parameters to an object; it is not a way to decode a JSON document in the request body. If the client sends JSON such as `{"name":"An"}`, use `@RequestBody`. For form/query/path input, `@ModelAttribute` is the appropriate choice.

## 2. How does Spring create and bind the object?

The usual process:

~~~text
HTTP request
    |
    +-- query parameters
    +-- form fields
    +-- URI path variables
    +-- request headers
    |
    v
@ModelAttribute argument
    |
    v
Find the object in the Model
    | if not found
    v
Create the object
    | constructor binding and/or property binding
    v
WebDataBinder
    | type conversion, formatting, validation
    v
Controller method receives the bound object
~~~

The object can be obtained from:

1. A model to which it was previously added with `Model.addAttribute(...)`.
2. A method annotated with `@ModelAttribute` in the controller or `@ControllerAdvice`.
3. The session, if managed through `@SessionAttributes`.
4. A default constructor or a constructor suited to the request data.

If no attribute is found, Spring can create it with the default constructor or a primary constructor with matching parameters. After that, under the default configuration, Spring can apply **constructor binding and property binding**.

An example of a mutable form object:

~~~java
public class ProfileForm {
    private String displayName;
    private String email;

    public ProfileForm() {
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

When the request sends `displayName=An&email=an@example.com`, Spring can create a `ProfileForm` through the empty constructor and then call the corresponding setters to bind the data.

## 3. Constructor binding and property binding

Spring supports two main ways of binding data:

| Binding approach | Mechanism | When suitable |
| --- | --- | --- |
| **Constructor binding** | Uses request data as arguments to the constructor | Immutable DTOs, records, input models with a clear set of properties |
| **Property binding** | Creates the object, then assigns through setters or writable properties | Mutable form objects that need properties updated |
| **Combined** | By default, both constructor and property binding can be used | A dedicated DTO designed to be safe for both |

### Constructor binding

You can use a Java record as the input object:

~~~java
public record SearchForm(String keyword, int page) {
}
~~~

Controller:

~~~java
@GetMapping("/search")
public SearchResult search(@ModelAttribute SearchForm form) {
    return searchService.find(form.keyword(), form.page());
}
~~~

Constructor binding is a good fit because a record is immutable and the constructor makes clear which data the application accepts. It also avoids a client sending arbitrary extra fields and then invoking setters on sensitive properties.

If the external field name differs from the constructor parameter name, you can use `@BindParam` to map it:

~~~java
public record SearchForm(
    @BindParam("page-size") int pageSize,
    String keyword
) {
}
~~~

The request can send `page-size=20&keyword=reactor`. `@BindParam` can be placed on the constructor parameter or the corresponding field; you need to import `org.springframework.web.bind.annotation.BindParam`.

### Property binding

Property binding is convenient for forms with setters:

~~~java
public class AddressForm {
    private String city;
    private String postalCode;

    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }

    public String getPostalCode() { return postalCode; }
    public void setPostalCode(String postalCode) { this.postalCode = postalCode; }
}
~~~

The request can send `city=Da+Nang&postalCode=550000`. Spring converts the strings and assigns them to the corresponding properties.

However, by default property binding can assign **any writable property** if the request name matches. Therefore, you should not bind JPA/Hibernate entities or large domain objects directly from client data. A client can add parameters for properties that were not meant to be editable, such as `role=ADMIN`, `accountEnabled=true`, `creditLimit=...`.

## 4. Designing safe input objects: avoiding mass assignment

**Mass assignment** happens when an application binds request parameters too broadly into an object that has sensitive properties. If an entity has `role`, `ownerId`, `approved`, or `balance`, a client can try sending those parameters even though the normal UI does not display them.

An unsafe example:

~~~java
// Do not use a domain entity directly as form input.
@PostMapping("/users")
public Mono<UserEntity> update(@ModelAttribute UserEntity user) {
    return repository.save(user);
}
~~~

This illustrative code can allow the request to bind to many properties that the endpoint did not intend to expose. Hiding a field in the UI is not a security mechanism.

Ways to prevent it, in the order you should consider them:

1. **Use a dedicated DTO/form object** that contains only the data the client is allowed to send.
2. Prefer **constructor binding** for immutable input models when appropriate.
3. If you need property binding, declare an **allow-list** with `WebDataBinder.setAllowedFields(...)`.
4. Use domain objects/entities only after you have clearly controlled which properties may be bound and the business permissions.
5. Check ownership and authorization in the service; an allow-list does not replace a permission check.

### Restricting properties with @InitBinder

`@InitBinder` lets you customize `WebDataBinder` before binding. You can restrict the allowed fields:

~~~java
@InitBinder("profileForm")
void initProfileBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
}
~~~

The name `profileForm` must match the model attribute name declared in the controller:

~~~java
@PostMapping("/profiles")
public ProfileView update(
        @ModelAttribute("profileForm") ProfileForm form) {
    return new ProfileView(form.getDisplayName(), form.getEmail());
}
~~~

With this configuration, a request that also contains `role=ADMIN` is not allowed to bind to the `role` property, even if the class has a setter for that property. `allowedFields` is an allow-list; field names are case-sensitive and support patterns/property paths according to Spring's rules.

If you need to use only constructor binding, you can enable declarative binding mode:

~~~java
@InitBinder("searchForm")
void initSearchBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
~~~

This mode always allows constructor binding and allows property binding only when `allowedFields` is declared. It is the right choice when you want to guarantee that data enters only through clearly designed constructor parameters.

`setDisallowedFields(...)` also exists, but an allow-list is usually safer and easier to maintain: when a new property is added to the domain object, the allow-list does not automatically open binding for that field.

## 5. Customizing data binding with @InitBinder

Besides restricting fields, `@InitBinder` is also used to register formatters, editors, converters, or to customize binding characteristics.

Example of restricting fields and applying it to the exact model attribute:

~~~java
@Controller
public class ProfileController {

    @InitBinder("profileForm")
    void configureProfileBinder(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "email");
    }

    // Handler methods...
}
~~~

You can omit the name in `@InitBinder` to apply it to multiple model attributes in the controller. If placed in a `@ControllerAdvice`, the configuration can be shared across a group of controllers within the advice's scope.

### Data conversion

Request values usually arrive as strings. Spring can convert them to target types such as `int`, `long`, `boolean`, enums, date/time, or types that have a suitable converter.

Example:

~~~java
public class SearchForm {
    private int page;
    private LocalDate fromDate;

    // getters/setters
}
~~~

Request:

~~~text
GET /search?page=2&fromDate=2026-05-01
~~~

If the date format is not the default or you need a custom format, you can register a `Formatter` or `Converter` through the binder/configuration. Do not parse every string value yourself in the controller when the Spring conversion service can manage it consistently.

### Attribute name and binder

Using an explicit name makes the link between `@ModelAttribute` and `@InitBinder` clear:

~~~java
@InitBinder("profileForm")
void init(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
}

@PostMapping("/profiles")
public ProfileView save(
        @ModelAttribute("profileForm") ProfileForm form) {
    // ...
}
~~~

If you omit the name in `@ModelAttribute`, Spring infers a default name from the object's type by convention. For a binder with a name-specific allow-list, you should declare the name explicitly to avoid a configuration that is not applied to the intended attribute.

## 6. Validation after binding

Data binding turns request data into an object; **validation checks whether that object satisfies business/format rules**. The two steps are related but different.

You can use Jakarta Bean Validation:

~~~java
public class ProfileForm {
    @NotBlank
    private String displayName;

    @NotBlank
    @Email
    private String email;

    // getters/setters
}
~~~

Mark the parameter with `@Valid` or `@Validated`:

~~~java
@PostMapping("/profiles")
public ProfileView save(
        @Valid @ModelAttribute("profileForm") ProfileForm form) {
    return new ProfileView(form.getDisplayName(), form.getEmail());
}
~~~

When validation fails, WebFlux by default raises `WebExchangeBindException`; an exception handler can map it to HTTP 400 Bad Request. In Spring Boot, a Bean Validation implementation is required, usually brought in through the `spring-boot-starter-validation` dependency.

### Getting errors with BindingResult

If you want to handle errors directly in the controller method, declare `BindingResult` **immediately after** the `@ModelAttribute` parameter:

~~~java
@PostMapping("/profiles")
public ResponseEntity<?> save(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        List<String> messages = errors.getFieldErrors().stream()
            .map(error -> error.getField() + ": " + error.getDefaultMessage())
            .toList();

        return ResponseEntity.badRequest()
            .body(Map.of("errors", messages));
    }

    return ResponseEntity.ok(
        new ProfileView(form.getDisplayName(), form.getEmail())
    );
}
~~~

`BindingResult` must come immediately after the model attribute it describes; if another parameter is placed in between, Spring cannot associate the error result with the right object as expected.

### Validation with Mono<T>

WebFlux supports reactive wrappers in a model attribute, for example `Mono<ProfileForm>`:

~~~java
@PostMapping("/profiles/reactive")
public Mono<ProfileView> saveReactive(
        @Valid @ModelAttribute("profileForm") Mono<ProfileForm> form) {
    return form.map(value ->
        new ProfileView(value.getDisplayName(), value.getEmail())
    );
}
~~~

In this case, you can handle validation errors through reactive error operators or let a shared exception handler manage them. If you want to receive a `BindingResult` as the next parameter, the model attribute must be an object **not wrapped in a reactive type**; do not declare `Mono<ProfileForm>` together with `BindingResult` that way.

If validation is performed as method validation because other parameters have constraints, the exception type may be `HandlerMethodValidationException`. You need to look at where validation actually occurs to choose the matching exception handler.

## 7. Distinguishing @ModelAttribute on a parameter and on a method

This annotation has two common uses with different purposes:

### On a method argument

Used to get/create the input object and bind the request to that object:

~~~java
@PostMapping("/profiles")
public ProfileView save(@ModelAttribute("profileForm") ProfileForm form) {
    // Use the bound data.
}
~~~

### On a controller or ControllerAdvice method

Used to **prepare model attributes before the handler method is called**:

~~~java
@ModelAttribute("supportedRegions")
public List<String> supportedRegions() {
    return List.of("VN", "SG", "JP");
}
~~~

`@ModelAttribute` methods in a controller are called before that controller's request mapping methods. The return value is added to the model under the attribute name; this usage is often useful for HTML views, lists of choices, or data shared across a form.

You can place a method-level `@ModelAttribute` in a `@ControllerAdvice` to share model data among multiple controllers. It is not an independent endpoint handler and does not replace `@RequestBody`.

## 8. How do @ModelAttribute, @RequestParam, and @RequestBody differ?

| Annotation | Data received | Target type | Typical use |
| --- | --- | --- | --- |
| `@ModelAttribute` | Query, form data, URI path variables, headers | Object/command object, can be a reactive wrapper in WebFlux | Many input fields gathered into a DTO |
| `@RequestParam` | One specific request parameter | A single value or collection | `page=2`, `keyword=spring` |
| `@RequestBody` | The HTTP request body content via a message reader/codec | DTO, `Mono<T>`, `Flux<T>` depending on the format | JSON/XML or a streaming body |
| `@RequestPart` | A part of a multipart request | DTO, file/part, or reactive part | File upload with metadata |

Example:

~~~java
@GetMapping("/search")
public SearchResult search(
        @RequestParam(defaultValue = "1") int page,
        @ModelAttribute SearchForm filter) {
    return searchService.search(page, filter);
}

@PostMapping(path = "/json", consumes = MediaType.APPLICATION_JSON_VALUE)
public Mono<ProfileView> createJson(
        @RequestBody Mono<ProfileForm> body) {
    return body.map(form ->
        new ProfileView(form.getDisplayName(), form.getEmail())
    );
}
~~~

The first example receives a separate `page` parameter and gathers the filter fields into `SearchForm`; the second example reads the JSON body through a codec. Choose the annotation based on the **actual data source** of the request, not just on the Java type of the parameter.

## 9. Complete Java 17+ example with Spring Boot WebFlux

This example receives a URL-encoded form, restricts the fields allowed to bind, checks validation, and returns specific errors. It has two endpoints:

- `POST /profiles`: uses `ProfileForm` directly together with `BindingResult`.
- `POST /profiles/reactive`: uses `Mono<ProfileForm>` and lets validation errors flow through the reactive pipeline.

Create the structure:

~~~text
model-attribute-demo/
├── pom.xml
└── src/main/java/com/example/modelattribute/
    ├── ModelAttributeApplication.java
    └── ProfileController.java
~~~

The `pom.xml` file:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>model-attribute-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
~~~

The `src/main/java/com/example/modelattribute/ModelAttributeApplication.java` file:

~~~java
package com.example.modelattribute;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ModelAttributeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ModelAttributeApplication.class, args);
    }
}
~~~

The `src/main/java/com/example/modelattribute/ProfileController.java` file:

~~~java
package com.example.modelattribute;

import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/profiles")
public class ProfileController {

    public static class ProfileForm {
        @NotBlank
        private String displayName;

        @NotBlank
        @Email
        private String email;

        // Sensitive field: the client is not allowed to bind it.
        private String role;

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }

        public String getRole() {
            return role;
        }

        public void setRole(String role) {
            this.role = role;
        }
    }

    public record ProfileView(
        String displayName,
        String email,
        String role
    ) {}

    @InitBinder("profileForm")
    void initProfileBinder(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "email");
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<?> create(
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            List<String> messages = errors.getFieldErrors().stream()
                .map(error ->
                    error.getField() + ": " + error.getDefaultMessage())
                .toList();

            return ResponseEntity.badRequest()
                .body(new ErrorView(messages));
        }

        return ResponseEntity.ok(
            new ProfileView(
                form.getDisplayName(),
                form.getEmail(),
                form.getRole()
            )
        );
    }

    @PostMapping(
        path = "/reactive",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ProfileView> createReactive(
            @Valid @ModelAttribute("profileForm") Mono<ProfileForm> form) {

        return form.map(value ->
            new ProfileView(
                value.getDisplayName(),
                value.getEmail(),
                value.getRole()
            )
        );
    }

    public record ErrorView(List<String> errors) {}
}
~~~

Run from the `model-attribute-demo` directory with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

### Try submitting a valid form

~~~bash
curl -i -X POST http://localhost:8080/profiles   -H "Content-Type: application/x-www-form-urlencoded"   --data-urlencode "displayName=An"   --data-urlencode "email=an@example.com"   --data-urlencode "role=ADMIN"
~~~

Expected response JSON:

~~~json
{
  "displayName": "An",
  "email": "an@example.com",
  "role": null
}
~~~

The client sent `role=ADMIN`, but `@InitBinder` only allows `displayName` and `email`, so `role` is not assigned. This is a concrete illustration of an allow-list for property binding.

### Try invalid data

~~~bash
curl -i -X POST http://localhost:8080/profiles   -H "Content-Type: application/x-www-form-urlencoded"   --data-urlencode "displayName="   --data-urlencode "email=not-an-email"
~~~

The direct endpoint receives `BindingResult`, so the method is called and returns HTTP 400 with a list of validation errors. The exact message text may vary depending on the Bean Validation provider and locale; the status and the presence of errors are what need to be checked.

### Try the reactive endpoint

~~~bash
curl -i -X POST http://localhost:8080/profiles/reactive   -H "Content-Type: application/x-www-form-urlencoded"   --data-urlencode "displayName=Binh"   --data-urlencode "email=binh@example.com"
~~~

Expected response JSON:

~~~json
{
  "displayName": "Binh",
  "email": "binh@example.com",
  "role": null
}
~~~

The reactive endpoint returns `Mono<ProfileView>`; WebFlux manages the subscription. If validation fails, the error is emitted during publisher resolution and handled by WebFlux's exception handling. There is no need to call `subscribe()` or `block()` in the controller.

The example is a complete Boot application at demo level; it is not connected to a database and does not store profiles. In a real system, the service needs to perform authorization and check update permissions beyond the binding restrictions.

## 10. Common mistakes

1. **Using `@ModelAttribute` to read a JSON body:** wrong data source. Use `@RequestBody` and the JSON codec.
2. **Binding a JPA entity directly:** can let the client modify unintended fields. Use a dedicated DTO/form object and an allow-list.
3. **Only hiding sensitive fields in the UI:** a client can send parameters on its own. Control it with server-side binding and authorization.
4. **Forgetting the attribute name in `@InitBinder`:** the binder may not apply to the intended model attribute. Use a consistent explicit name in both annotations.
5. **Assuming `@InitBinder` is where permissions are checked:** allowedFields only restricts property binding; the service must still check whether the user has permission to modify the object.
6. **Placing `BindingResult` away from the model attribute parameter:** Spring does not attach the errors to the right argument. Place it immediately after `@ModelAttribute`.
7. **Combining `BindingResult` with a `Mono<T>` model attribute:** not a way WebFlux supports. If you use BindingResult, the model attribute parameter must have no reactive wrapper.
8. **Confusing validation with binding:** binding converts data; validation checks constraints. A string that cannot be converted to a number can cause a binding error before business validation runs.
9. **Using `@Valid` but lacking a Bean Validation provider:** the annotation does not supply an implementation by itself. Add an appropriate dependency such as `spring-boot-starter-validation`.
10. **Allowing too many nested properties:** a property path can reach child objects, lists, or maps. Only open the paths that are truly necessary in the allow-list.
11. **Using `disallowedFields` as the only protection:** a deny-list easily falls short when the domain adds new fields. Prefer `allowedFields`.
12. **Using a mutable form object without controlling setters:** property binding only works with writable properties and can expand beyond what was expected. Design a clear DTO.
13. **Assuming query parameters and path variables always have equal priority:** request parameters/form take precedence over path variables and headers when names collide.
14. **Reading a JSON body with `@ModelAttribute`:** a body document is not a set of form/query parameters; use `@RequestBody`.
15. **Calling `subscribe()` or `block()` in a reactive controller:** detaches the pipeline from the request lifecycle or blocks the event loop. Compose the publisher and return the result to WebFlux.
16. **Believing an allow-list replaces authorization:** a field being allowed to bind does not mean the user has permission to modify that object. Check ownership, tenant, and permission in the service.

## 11. Checklist before putting @ModelAttribute into production

- The model attribute contains only the input fields the endpoint truly accepts.
- The right data source has been chosen: query, form, path/header, or JSON body.
- The model attribute name is explicit if there is a name-specific `@InitBinder` configuration.
- Constructor binding/records have been considered for immutable input.
- If using property binding, `allowedFields` opens only the necessary properties.
- Domain entities with sensitive fields are not bound directly.
- `@Valid`/`@Validated` has been declared and binding/validation errors are handled.
- If using `BindingResult`, it comes immediately after a non-reactive object.
- If using `Mono<T>`, errors are handled reactively or via an exception handler.
- Authorization and ownership checks exist independently of binding.
- Input length/value limits exist and nested collections are handled reasonably.
- The controller does not subscribe/block on its own.

## 12. Self-check questions

**1.** What does `@ModelAttribute` do? It creates or retrieves a model object and binds request data to that object through `WebDataBinder`.

**2.** In WebFlux, what are the main data sources of `@ModelAttribute`? Query parameters, form data, URI path variables, and request headers.

**3.** Does `@ModelAttribute` read a JSON body instead of `@RequestBody`? No. A JSON body uses a message reader/codec via `@RequestBody`.

**4.** How does constructor binding differ from property binding? Constructor binding passes input into the constructor; property binding assigns through setters/writable properties.

**5.** Why should you not bind a JPA entity directly? A request can assign sensitive properties that the endpoint did not intend to allow changing.

**6.** What are `@InitBinder` and `setAllowedFields` used for? Configuring the binder and restricting the list of properties allowed to bind.

**7.** Why use a dedicated DTO? The DTO contains only the input allowed to be received, clarifies the API contract, and reduces the risk of mass assignment.

**8.** Where must `BindingResult` be placed? Immediately after the `@ModelAttribute` parameter it describes.

**9.** Can you use `Mono<ProfileForm>` with `BindingResult` right after it? Not in the way WebFlux supports; use a non-reactive object if you need BindingResult, or handle errors reactively when using Mono.

**10.** Does `@Valid` replace authorization? No. Validation checks the data; authorization checks the permission to perform the action.

**11.** What does `@ModelAttribute` on a method mean? It puts the return value into the model or prepares the model before the request mapping method runs.

**12.** If the client also sends `role=ADMIN` but the allow-list only has `displayName,email`, what happens? The `role` field is not allowed to bind; the service still needs its own permission check.

**Remember:** `@ModelAttribute` binds **query/form/path/header input** to a typed object. `WebDataBinder` performs constructor/property binding, conversion, and validation. In WebFlux you can receive the object directly or a reactive wrapper such as `Mono<T>`. For safety, use a dedicated DTO or constructor binding; if you need property binding, restrict it with `@InitBinder` and `setAllowedFields`. Validation, authorization, and the reactive lifecycle must still be handled correctly at their respective layers.

**Official documentation:** [Spring Framework 6.2 — @ModelAttribute in WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html); [Spring Framework 6.2 — Data Binding in WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/data-binding.html); [Spring Framework 6.2 — @InitBinder in WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-initbinder.html).