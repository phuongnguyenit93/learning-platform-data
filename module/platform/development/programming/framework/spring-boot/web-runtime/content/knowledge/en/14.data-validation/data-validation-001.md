# Setting Up Bean Validation and spring-boot-starter-validation in Spring Boot

## Learning Objectives

When writing an API, syntactically valid JSON data is not necessarily valid from a business perspective: an email may be empty, age may be negative, price may be negative, or a child object may be missing properties. **Jakarta Bean Validation** allows expressing these basic rules directly on data types using constraint annotations and checking them via a validation provider. In Spring Boot, **spring-boot-starter-validation** is the standard way to add this infrastructure.

After this lesson, you will be able to:

- Distinguish between the Jakarta Validation API, Hibernate Validator, Spring Validator, @Valid, and @Validated.
- Install spring-boot-starter-validation with Maven/Gradle and recognize the difference between javax.validation and jakarta.validation.
- Use @NotNull, @NotBlank, @NotEmpty, @Size, @Min, @Max, @Email, @Positive, @Past, @Future, and other appropriate constraints.
- Enable validation of @RequestBody in Spring MVC and WebFlux; validate nested objects with @Valid.
- Understand validation for method parameters/services via @Validated and the limitations when using AOP proxies.
- Handle validation errors as HTTP 400 without exposing sensitive data, while distinguishing validation errors from JSON parse errors.
- Use Validator to validate data outside the web layer, write custom constraints, and customize messages.
- Test a Java 17+ REST API with MockMvc and common edge cases.

## 1. Distinguishing the Layers in the Validation System

| Component | Function | Example |
|---|---|---|
| Jakarta Validation | Defines the standard annotations/API to declare and evaluate constraints | jakarta.validation.Valid, Validator, ConstraintViolation |
| Hibernate Validator | A popular implementation of Jakarta Validation | Executes logic for @NotBlank, @Email, @Size |
| spring-boot-starter-validation | Spring Boot starter providing the required validation dependencies | Maven/Gradle dependency |
| Spring Validation | Integrates constraint validation with binding, controllers, and services | LocalValidatorFactoryBean, BindingResult |
| @Valid | Requests constraint evaluation on an object and cascades into marked child objects | jakarta.validation.Valid |
| @Validated | Spring annotation used to enable method validation on a bean/class or select validation groups | org.springframework.validation.annotation.Validated |
| Constraint annotation | Describes a validity condition | @NotNull, @Size, @Min, @Email |
| ConstraintValidator | Implementation for a custom-defined constraint | Validates an order code against custom rules |

Visualizing the flow with a REST API:

~~~text
HTTP request JSON
       |
       v
Spring MVC HttpMessageConverter / WebFlux codec
       |
       v
Deserialize into DTO
       |
       +--- @Valid / @Validated declared appropriately?
       |             |
       |             v
       |       Jakarta Validation API
       |             |
       |             v
       |       Hibernate Validator (provider)
       |             |
       |      +------+------+
       |      |             |
       |     PASS          FAIL
       |      |             |
       v      v             v
   Controller          validation exception
       |                     |
       v                     v
   Business logic       HTTP 400 / error handler
       |
       v
   HTTP response
~~~

**Note:** Jackson is responsible for reading JSON into an object, not replacing Bean Validation. @Valid does not make syntactically invalid JSON valid. Likewise, a constraint like @Min does not by itself prove every business rule; for example, “whether an email is already registered” typically requires looking up a service/database.

## 2. Adding spring-boot-starter-validation

### 2.1. Maven

With a Spring Boot parent or BOM managing versions:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

For a Spring Boot 3.5 Spring MVC project, also include the web starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

### 2.2. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

### 2.3. Spring Boot 4.x

According to the Spring Boot 4 migration guide, the validation starter name remains **spring-boot-starter-validation**. However, the MVC starter is split/named specifically **spring-boot-starter-webmvc**; use the dependency corresponding to your actual version. Boot 4 also introduces corresponding test starters, such as spring-boot-starter-validation-test; do not copy the Boot 3.5 Maven dependencies verbatim into Boot 4 without checking the migration guide.

All main runnable Java examples in this lesson target **Java 17+, Spring Boot 3.5.x, Jakarta Validation**. To ensure compatibility, let the Spring Boot BOM select the versions of Hibernate Validator and the Jakarta libraries.

### 2.4. Why does the validation starter need to be declared explicitly?

In modern Spring Boot generations, you should not assume that adding the web starter automatically provides a validation provider. If the API classes are present without a provider, constraints may not be evaluated as expected.

Symptoms you may encounter:

- @Valid is added to a controller, yet data violating constraints still slips through.
- Dependency resolution is missing Hibernate Validator or Jakarta Validation classes.
- Startup fails with an error related to ValidatorFactory/ValidationProvider.
- A service is not blocked even though a method has @NotBlank and @Validated.

Inspect the dependency tree instead of randomly adding multiple validation implementations:

~~~bash
./mvnw dependency:tree
~~~

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Usually, only the validation starter is needed for Boot to set up an appropriate provider and adapter. You do not need to manually add a Hibernate Validator version or manually configure LocalValidatorFactoryBean unless you have special requirements.

## 3. Jakarta Validation and the Package Difference javax → jakarta

In modern Spring Boot 3.x and 4.x applications, use:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
~~~

In older Spring Boot 2.x projects, you often see:

~~~java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
~~~

These two namespaces cannot be swapped arbitrarily. An example on the internet written with javax.validation may not compile or integrate as expected in Spring Boot 3+.

| Application | Standard Namespace |
|---|---|
| Spring Boot 2.x / Spring Framework 5 | javax.validation.* |
| Spring Boot 3.x / Spring Framework 6 | jakarta.validation.* |
| Spring Boot 4.x / Spring Framework 7 | jakarta.validation.* |

Do not add both javax and jakarta dependencies to “resolve” import errors. Choose Jakarta to match your project stack and replace old dependencies in a controlled way.

## 4. Common Constraints

| Constraint | Used for | Common Meaning |
|---|---|---|
| @NotNull | Reference types | Must be non-null; does not guarantee a non-empty String |
| @NotEmpty | CharSequence, Collection, Map, Array... | Non-null and non-empty; a string of only spaces is still considered non-empty |
| @NotBlank | CharSequence | Non-null and must contain at least one non-whitespace character |
| @Size(min, max) | String/Collection/Array/Map... | Limits length/element count; does not necessarily reject null |
| @Min(n), @Max(n) | Supported numeric types | Minimum/maximum (inclusive) |
| @Positive, @PositiveOrZero | Supported numeric types | Greater than 0 / greater than or equal to 0 |
| @Negative, @NegativeOrZero | Supported numeric types | Less than 0 / less than or equal to 0 |
| @DecimalMin, @DecimalMax | Supported numeric types | Decimal bounds with inclusive/exclusive configuration |
| @Digits(integer, fraction) | Numbers or supported numeric representations | Limits integer/fractional digit counts |
| @Email | CharSequence | Checks email structure per provider; does not verify mailbox existence |
| @Pattern(regexp) | CharSequence | Matches a regular expression |
| @Past, @PastOrPresent | Supported date/time types | A point in the past or not after the present |
| @Future, @FutureOrPresent | Supported date/time types | A point in the future or not before the present |
| @AssertTrue, @AssertFalse | Boolean/boolean | Boolean rule |
| @Valid | Child objects/collection elements | Requests cascade validation; not a constraint itself |

### Big Trap: @NotNull, @NotEmpty, and @NotBlank Are Different

Suppose the value is a String:

| Value | @NotNull | @NotEmpty | @NotBlank |
|---|---|---|---|
| null | FAIL | FAIL | FAIL |
| "" | PASS | FAIL | FAIL |
| "   " | PASS | PASS | FAIL |
| "abc" | PASS | PASS | PASS |

Therefore, a required username or email should usually use @NotBlank instead of only @NotNull.

### @Size vs. @Min

@Size(min = 3) checks length or element count for supported types. @Min(3) checks that a numeric value is at least 3; do **not** use @Min(3) to require a String to have 3 characters.

Example:

~~~java
@NotBlank
@Size(min = 2, max = 50)
String name;

@NotNull
@Min(18)
Integer age;
~~~

These snippets illustrate fields in a DTO/class. For Integer, @NotNull is necessary because many numeric constraints accept null and only check when a value is present.

### @Email Does Not Replace Email Verification

@Email validates format according to the provider; it does not check MX records, email deliverability, or mailbox ownership. If the email field is required:

~~~java
@NotBlank
@Email
String email;
~~~

Do not use @Email alone and assume it forbids null, empty strings, or whitespace in all cases. Combine it with @NotBlank per your API contract.

## 5. When Does Validation Run?

Annotations do not run automatically as if “creating an object validates it”. Validation must be triggered at an execution point:

1. Spring MVC processes @Valid @RequestBody or @Validated on a supported argument.
2. WebFlux processes @Valid @RequestBody under the reactive contract.
3. Spring method validation checks method parameters/return values via @Validated and proxy/handler method integration.
4. You call Validator.validate(object) directly.
5. A non-web system integrates Jakarta Validation into persistence or another lifecycle.

Example creating a DTO manually with new:

~~~java
SignupRequest request =
    new SignupRequest("", "not-email", null);
~~~

The Java object can still be created; annotations on record components do not automatically throw exceptions from the constructor. To validate outside the web layer, call Validator or pass through a validation-enabled service/method.

## 6. How Do @Valid and @Validated Differ?

### Jakarta @Valid

~~~java
import jakarta.validation.Valid;
~~~

This is the standard annotation used to mark an object requiring cascade validation or to request validation at framework-supported integration points. Example:

~~~java
@PostMapping("/api/users")
public ResponseEntity<UserView> create(
        @Valid @RequestBody SignupRequest request) {
    // ...
}
~~~

In Spring MVC, if the DTO violates constraints, the framework normally returns 400 before the business method runs (or lets an exception handler handle it).

### Spring @Validated

~~~java
import org.springframework.validation.annotation.Validated;
~~~

@Validated supports validation groups and is commonly used on service types when enabling Spring method validation via an AOP proxy:

~~~java
@Service
@Validated
public class UserService {
    public void register(@NotBlank String email) {
        // ...
    }
}
~~~

This example only works as intended if the service is managed by Spring, the method call goes through a proxy, and an appropriate validation provider/method validation infrastructure is configured. Direct calls like new UserService() are not checked by Spring.

### Controller Rule in Spring Framework 6.1+

Spring MVC has **built-in method validation** for controllers when constraints are placed directly on method parameters or return values. To use this mechanism instead of an AOP proxy for controllers, the Spring Framework documentation advises **against** placing @Validated at the controller class level mechanically.

Example:

~~~java
@GetMapping("/api/users/{id}")
public UserView find(@PathVariable @Min(1) long id) {
    // ...
}
~~~

With built-in handler method validation, a constraint on id can lead to HandlerMethodValidationException when the value is invalid. This differs from an error on a @Valid @RequestBody DTO. Do not assume every validation error in a controller is a MethodArgumentNotValidException.

## 7. How to Enable Validation for @RequestBody in Spring MVC

A complete DTO using a record:

~~~java
package com.example.validation;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record SignupRequest(
        @NotBlank(message = "email is required")
        @Email(message = "invalid email format")
        String email,

        @NotBlank(message = "name is required")
        @Size(min = 2, max = 50, message = "name must be 2–50 characters")
        String name,

        @NotNull(message = "age is required")
        @Min(value = 18, message = "must be at least 18 years old")
        Integer age
) {
}
~~~

When a controller method declares @Valid @RequestBody SignupRequest, Spring will:

1. Read the JSON body.
2. Deserialize it into SignupRequest (Jackson).
3. Run constraints implemented by the provider.
4. If PASS, pass the object into the controller.
5. If FAIL, take the validation error branch; in typical argument validation scenarios this is MethodArgumentNotValidException and HTTP 400 under the default handler.

### Why Integer Instead of int?

If a JSON request omits the age field, Integer can be null so @NotNull detects the missing data. If int is used, deserialization/binding may produce a default value or throw a different kind of error depending on the mapper and input. For required fields where missing/null must be distinguished from a valid number, a wrapper type usually gives a clearer contract.

### Valid JSON Does Not Mean Valid Data

Request:

~~~json
{
  "email": "not-an-email",
  "name": " ",
  "age": 16
}
~~~

This is syntactically valid JSON and can be deserialized into a Java record, but it violates @Email, @NotBlank/@Size, and @Min.

Syntactically invalid request:

~~~json
{"email": "an@example.com", "name":
~~~

Here, the decoder/parser may throw HttpMessageNotReadableException before Bean Validation is even applied. Message conversion errors must be distinguished from constraint violations.

## 8. Complete Spring Boot REST API Example (Java 17+)

This runnable example targets **Spring Boot 3.5.x**, Java 17+ with Maven Wrapper. Choose **Spring Web**, **Validation**, and, for testing, **Spring Boot Test**. If Maven does not have a wrapper, use the corresponding mvn spring-boot:run command.

### 8.1. Dependencies

In the pom.xml of a Spring Boot project with parent/BOM:

~~~xml
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
~~~

### 8.2. ValidationApplication.java

File: src/main/java/com/example/validation/ValidationApplication.java

~~~java
package com.example.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationApplication.class, args);
    }
}
~~~

### 8.3. SignupRequest.java

Use the complete record content from section 7. You do not need to write getters/setters when the DTO is a Java 17 record with compatible Jackson/Bean Validation versions.

### 8.4. UserView.java

File: src/main/java/com/example/validation/UserView.java

~~~java
package com.example.validation;

public record UserView(
        long id,
        String email,
        String name,
        int age
) {
}
~~~

### 8.5. UserController.java

File: src/main/java/com/example/validation/UserController.java

~~~java
package com.example.validation;

import java.net.URI;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/users")
public class UserController {

    private final AtomicLong sequence = new AtomicLong();

    @PostMapping
    public ResponseEntity<UserView> create(
            @Valid @RequestBody SignupRequest request) {

        long id = sequence.incrementAndGet();

        UserView result = new UserView(
            id,
            request.email().trim(),
            request.name().trim(),
            request.age()
        );

        return ResponseEntity
            .created(URI.create("/api/users/" + id))
            .body(result);
    }

    @GetMapping("/{id}")
    public ResponseEntity<UserView> find(@PathVariable long id) {
        return ResponseEntity.notFound().build();
    }
}
~~~

Note: GET here always returns 404 because the example **does not store users in a database/in-memory**, only illustrating POST validation. This is intentional behavior, not a validation bug. If you want GET to return real data, you need to add a repository/service and persistence.

What is worth learning is that the controller **does not need** to repeatedly check email/name/age with multiple if statements; the DTO together with @Valid expresses the constraints before creating the response.

### 8.6. ValidationErrorAdvice.java

To return structured 400 errors, you can handle MethodArgumentNotValidException in Spring MVC:

~~~java
package com.example.validation;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ValidationErrorAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> invalidBody(
            MethodArgumentNotValidException ex) {

        Map<String, String> errors = new LinkedHashMap<>();

        ex.getBindingResult().getFieldErrors().forEach(fieldError ->
            errors.putIfAbsent(
                fieldError.getField(),
                fieldError.getDefaultMessage()
            )
        );

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("message", "Invalid data");
        body.put("errors", errors);

        return ResponseEntity.badRequest().body(body);
    }
}
~~~

Why use putIfAbsent: a field can violate multiple constraints; the demo only returns the first message per field without guaranteeing the order of validation errors. If your API needs to return **all** errors per field, use Map<String,List<String>> or a list of error objects instead of collapsing to a single error.

In real products, you can use **ProblemDetail** (Spring Framework 6+) and a unified error contract. Do not echo raw passwords/tokens or full rejected values in the response. Validation messages can be localized using Locale/MessageSource.

**Handling limitation of this advice:** It only catches @Valid @RequestBody errors belonging to MVC's MethodArgumentNotValidException branch. It does not automatically catch HandlerMethodValidationException, JSON parse errors, or service validation errors. Those cases must be handled separately when used by the API.

### 8.7. Running and Testing with curl

From the project root:

~~~bash
./mvnw spring-boot:run
~~~

On Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Send a valid request:

~~~bash
curl -i -X POST http://localhost:8080/api/users \
  -H "Content-Type: application/json" \
  -d '{"email":"an@example.com","name":"An Nguyen","age":20}'
~~~

On a freshly started application, sequence starts at 0. The first successful response has status **201 Created**, header **Location: /api/users/1**, and a JSON body equivalent to:

~~~json
{"id":1,"email":"an@example.com","name":"An Nguyen","age":20}
~~~

Send invalid data:

~~~bash
curl -i -X POST http://localhost:8080/api/users \
  -H "Content-Type: application/json" \
  -d '{"email":"wrong-format","name":" ","age":16}'
~~~

The expected response is **400 Bad Request** with a body containing a message field and an errors map. The specific message value for name may come from @NotBlank or @Size, since both can fail; the order should not be used as an API contract.

An illustrative body (key order not guaranteed):

~~~json
{
  "message": "Invalid data",
  "errors": {
    "email": "invalid email format",
    "name": "name is required",
    "age": "must be at least 18 years old"
  }
}
~~~

If name returns the message "name must be 2–50 characters" in this environment, that is still a valid result of the constraint, not a framework bug.

### 8.8. Why Does the Example Use @Valid in the Controller?

Declaring constraints only on the DTO while writing the method like this leaves the validation point unspecified:

~~~java
@PostMapping
public ResponseEntity<UserView> create(
        @RequestBody SignupRequest request) {
    // ...
}
~~~

To ensure argument validation via Spring MVC integration, use **@Valid @RequestBody**. Do not assume every place receiving SignupRequest validates it automatically.

## 9. HTTP Testing with MockMvc

An important test checks not just whether JSON can be parsed, but also confirms status 201 for valid input and 400 when Bean Validation fails.

File: src/test/java/com/example/validation/UserControllerTest.java

~~~java
package com.example.validation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class UserControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void validPayloadCreatesUser() throws Exception {
        mockMvc.perform(post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"email":"an@example.com",
                     "name":"An Nguyen",
                     "age":20}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.email")
                .value("an@example.com"))
            .andExpect(jsonPath("$.age").value(20));
    }

    @Test
    void invalidPayloadIsRejectedBeforeControllerLogic() throws Exception {
        mockMvc.perform(post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"email":"wrong-format",
                     "name":" ",
                     "age":16}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.message")
                .value("Invalid data"))
            .andExpect(jsonPath("$.errors.email").exists())
            .andExpect(jsonPath("$.errors.name").exists())
            .andExpect(jsonPath("$.errors.age").exists());
    }
}
~~~

The tests do not compare specific IDs because a single Spring context may run multiple tests and AtomicLong is shared. The second test confirms all invalid fields have errors, without constraining message ordering when a field violates multiple constraints.

You should also add tests for: null email, empty name, missing age, name longer than 50 characters, malformed JSON, wrong media type, Unicode strings, and boundary values 18/17.

### Testing Validator Outside HTTP

With a Spring context that has the validation starter, you can inject Jakarta Validator to check plain DTOs:

~~~java
@Autowired
jakarta.validation.Validator validator;

@Test
void invalidDtoHasConstraints() {
    SignupRequest request =
        new SignupRequest("", " ", null);

    var violations = validator.validate(request);

    assertFalse(violations.isEmpty());
}
~~~

This is an illustrative method for a test class with proper JUnit and Spring imports, not a standalone file. If checking the set of messages, base assertions on propertyPath and constraint type or controlled message codes rather than relying on Set element order.

## 10. Nested Validation with @Valid

Suppose a request has an Address:

~~~java
public record Address(
    @NotBlank String city,
    @NotBlank String postalCode
) {
}
~~~

And a parent DTO:

~~~java
public record CheckoutRequest(
    @NotNull @Valid Address address,
    @NotEmpty String reference
) {
}
~~~

These snippets illustrate records and require importing jakarta.validation.Valid and the constraints.

Why do you need both **@NotNull @Valid**?

- @Valid marks that the inner properties need to be validated **when Address exists**.
- @NotNull rejects the case where address is missing or null.
- With only @Valid, a null address reference does not automatically produce a constraint violation.
- With only @NotNull, @NotBlank constraints inside Address may not be cascade-validated as intended.

With collections:

~~~java
public record BatchRequest(
    @NotEmpty
    java.util.List<@Valid Address> addresses
) {
}
~~~

Jakarta Validation supports container element validation for appropriate type-use locations. In practice, combine constraints on each element if you need to forbid null elements; @Valid by itself does not forbid a null element.

Example tag list:

~~~java
public record TagRequest(
    @NotEmpty
    java.util.List<@NotBlank String> tags
) {
}
~~~

Here @NotEmpty checks that the list has elements; @NotBlank checks each String in the list. Do not assume @NotEmpty on a List automatically checks the validity of every element.

## 11. Method Validation at the Service Layer with @Validated

Bean Validation is not limited to HTTP DTOs. A service can place constraints directly on method parameters or return values.

Example:

~~~java
package com.example.validation;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class EmailService {

    @NotNull
    public String normalize(
            @NotBlank @Email String address) {

        return address.trim().toLowerCase(
            java.util.Locale.ROOT
        );
    }
}
~~~

When this method is called **through a Spring-managed proxy**, method validation can check address before the method body runs and check the return value per the contract. For invalid arguments, the exception at the method validation layer is commonly **jakarta.validation.ConstraintViolationException** in standard configurations, though behavior can vary depending on the Spring/adapter mechanism used.

### Important Conditions

- The validation starter and a compatible provider are on the classpath.
- The service is a Spring-managed bean.
- @Validated is at the type level if using standard Spring Boot AOP method validation.
- The method is called from another bean through the proxy; self-invocation such as this.normalize("") can bypass the proxy.
- Private/final methods or methods not intercepted by the proxy per AOP configuration do not automatically get validation guarantees.
- Depending on JDK proxy/CGLIB and where annotations are declared, behavior may differ; do not treat annotations as standalone Java statements.

Do not use class-level @Validated on a controller just to “be sure to catch everything” if you want to use Spring Framework 6.1+ built-in handler method validation. See section 12 to distinguish controller errors.

### Service Validation Does Not Replace Business Logic

@Email does not check email uniqueness in the database. @Min(18) does not verify a real birth date. Rules such as user balance, inventory, permissions, and transaction invariants require logic in the service layer and appropriate database constraints. Validation is an input layer, not the sole security shield.

## 12. Two Validation Paths in Spring MVC/WebFlux

Since Spring Framework 6.1, annotated controllers have two primary validation paths.

### Path A: Validating an Object Argument

Example:

~~~java
@PostMapping("/api/orders")
public ResponseEntity<Void> create(
        @Valid @RequestBody OrderRequest request) {
    // ...
}
~~~

If the object data violates constraints and there are no other method-level constraints triggering method validation, Spring MVC normally throws **MethodArgumentNotValidException**. WebFlux normally uses **WebExchangeBindException**.

### Path B: Built-in Handler Method Validation

Example:

~~~java
@GetMapping("/api/orders/{id}")
public OrderView find(@PathVariable @Min(1) long id) {
    // ...
}
~~~

The @Min constraint placed **directly** on a method parameter makes the controller handler require method validation. Both Spring MVC and WebFlux can throw **HandlerMethodValidationException** in their respective built-in mechanisms.

### Comparison Table

| Case | Spring MVC | Spring WebFlux |
|---|---|---|
| @Valid on @RequestBody DTO, standalone argument validation | MethodArgumentNotValidException | WebExchangeBindException |
| Direct constraint @Min/@NotBlank on method parameter | HandlerMethodValidationException when built-in method validation applies | HandlerMethodValidationException when built-in method validation applies |
| @Validated service via AOP | Typically ConstraintViolationException/configuration variant | Typically ConstraintViolationException/configuration variant |
| Malformed JSON | HttpMessageNotReadableException | Typically appropriate request read/codec error, possibly ServerWebInputException |
| Default constraint failure | Usually HTTP 400 for request input | Usually HTTP 400 for request input |

**Both error paths need to be handled** if your application uses both @Valid DTOs and inline method constraints. Writing only @ExceptionHandler(MethodArgumentNotValidException.class) will not automatically cover HandlerMethodValidationException.

Do not assume a method return-value validation error is also a 400 request error: when the application violates constraints on its own output data, that may be a server-side error. Spring Framework distinguishes statuses depending on the case.

## 13. Validation in Spring WebFlux

Spring WebFlux also supports @Valid and @Validated, but works with reactive HTTP bodies. Example:

~~~java
@PostMapping("/api/users")
public Mono<ResponseEntity<UserView>> create(
        @Valid @RequestBody Mono<SignupRequest> request) {

    return request.map(valid -> {
        UserView view = new UserView(
            1L,
            valid.email(),
            valid.name(),
            valid.age()
        );

        return ResponseEntity
            .created(URI.create("/api/users/1"))
            .body(view);
    });
}
~~~

This is an illustrative method that must be placed inside a WebFlux @RestController with appropriate imports and the same DTO from the example. WebFlux supports validation when decoding a reactive request body at framework-supported integration points. Do not call block() just for validation. If you want custom error handling in WebFlux, handle WebExchangeBindException/HandlerMethodValidationException according to that stack's contract instead of copying MVC advice verbatim.

**Do not place @Valid on Mono mechanically in every signature without checking the documentation for your version.** The framework has specific rules for validating Publisher-valued @RequestBody and ways to validate Flux elements in a pipeline. When you need service-level validation or per-element Flux validation, design the publisher and constraint validation clearly and add WebTestClient tests for invalid data cases.

### WebTestClient Testing Reactive Validation

With a properly configured WebFlux endpoint test fixture:

~~~java
webTestClient.post()
    .uri("/api/users")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new SignupRequest(
        "wrong-format",
        " ",
        16
    ))
    .exchange()
    .expectStatus().isBadRequest();
~~~

This is a snippet inside a test that already has WebTestClient and MediaType, not a standalone file. What needs to be verified is that bad input is rejected with HTTP 400, not which thread invoked the validator.

## 14. Validation Messages and i18n

A constraint can have a message:

~~~java
@NotBlank(message = "name is required")
String name;
~~~

Or reference a message key:

~~~java
@NotBlank(message = "{user.name.required}")
String name;
~~~

When a MessageSource is properly configured, you can define in src/main/resources/messages.properties:

~~~properties
user.name.required=Name is required
~~~

If multiple languages are needed, place messages_vi.properties and messages_en.properties bundles according to the application's locale strategy. Spring Boot provides MessageSource auto-configuration under appropriate conditions; Jakarta Validation's message interpolation process also participates in resolving message templates.

**Do not depend on message order** when a field violates multiple constraints. The result of Validator.validate is a Set<ConstraintViolation<T>>; tests should compare field/property and constraint type or controlled message codes instead of Set element order.

Changing a message does not change validation logic. A String still fails @NotBlank whether the message is in Vietnamese or English.

## 15. Validation Groups: When Create and Update Have Different Rules

Jakarta Validation supports **validation groups** to use different sets of constraints depending on context.

Example declaring marker interfaces:

~~~java
public interface OnCreate {
}

public interface OnUpdate {
}
~~~

Place each public interface in its own file according to Java rules.

An illustrative DTO:

~~~java
public record ProductForm(
    @NotNull(groups = OnUpdate.class)
    Long id,

    @NotBlank(groups = {
        OnCreate.class,
        OnUpdate.class
    })
    String title
) {
}
~~~

In the controller, you can request a group:

~~~java
@PostMapping("/products")
public ResponseEntity<Void> create(
        @Validated(OnCreate.class)
        @RequestBody ProductForm form) {
    // ...
}
~~~

@Validated is a Spring extension supporting group selection during binding/validation. With plain @Valid, the default group is used at standard integration points.

**Default group trap:** A constraint declared only in OnCreate/OnUpdate does not automatically belong to the Default group. When a controller uses plain @Valid, constraints not belonging to Default may not run as you expect. Use groups intentionally and consistently across endpoints.

If create/update requirements differ significantly in schema, two separate DTOs CreateProductRequest/UpdateProductRequest are usually clearer and easier to maintain than one DTO with too many groups.

## 16. Custom Constraints: When Built-in Annotations Are Not Enough

Suppose an application needs to validate an order code in the format "ORD-" followed by four digits. You can create a custom constraint.

### 16.1. Annotation @OrderCode

File: src/main/java/com/example/validation/OrderCode.java

~~~java
package com.example.validation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Target({
    ElementType.FIELD,
    ElementType.PARAMETER,
    ElementType.RECORD_COMPONENT
})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = OrderCodeValidator.class)
public @interface OrderCode {

    String message() default "order code must match ORD-1234";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

### 16.2. Validator Implementation

File: src/main/java/com/example/validation/OrderCodeValidator.java

~~~java
package com.example.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class OrderCodeValidator
        implements ConstraintValidator<OrderCode, String> {

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {

        if (value == null) {
            return true;
        }

        return value.matches("ORD-[0-9]{4}");
    }
}
~~~

We return true for null because **requiredness** should be controlled by @NotNull or @NotBlank. Separating these two responsibilities allows the @OrderCode constraint to be reused for both optional and required fields.

### 16.3. Applying to a Record

~~~java
public record OrderCodeRequest(
    @NotBlank
    @OrderCode
    String orderCode
) {
}
~~~

For this snippet to compile, place it in OrderCodeRequest.java in the right package and import NotBlank. Input "ORD-1234" is valid; "ORD-12A4" or "ABC-1234" fails. The order code is just an illustrative format; it does not check existence in the database.

In a Spring environment, LocalValidatorFactoryBean can use SpringConstraintValidatorFactory to support dependency injection for custom ConstraintValidators. If a custom validator must read the database, consider cost and transactions; do not perform blocking HTTP/network calls on the WebFlux event loop carelessly.

### Why Not Turn Every Business Rule into a ConstraintValidator?

Custom constraints are suitable for pure data rules. If validation needs to know user permissions, inventory state, order version, or transaction consistency, execute it in the service/domain layer with an appropriate error contract and transactions/locking when needed.

## 17. Programmatic Validation: Validating Without an HTTP Controller

You can inject Validator into a service to validate DTO/command objects in a batch job, message listener, or other processing flow.

~~~java
package com.example.validation;

import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;

import org.springframework.stereotype.Service;

@Service
public class SignupValidationService {

    private final Validator validator;

    public SignupValidationService(Validator validator) {
        this.validator = validator;
    }

    public Set<ConstraintViolation<SignupRequest>> check(
            SignupRequest request) {
        return validator.validate(request);
    }
}
~~~

This is an explicit way to validate, independent of @RequestBody. Results can be mapped to batch/message consumer business errors or an appropriate HTTP response. Do not force every constraint violation outside HTTP to become 400; HTTP status only has meaning when building an HTTP response.

### Do Not Confuse the Two Validator Interfaces

- **jakarta.validation.Validator**: Standard API, returns Set<ConstraintViolation<T>>.
- **org.springframework.validation.Validator**: Spring API taking Errors to record field/global errors.
- **LocalValidatorFactoryBean**: Adapter that bridges both validation worlds in Spring.

When writing code, imports must match how you intend to use it. A variable of type org.springframework.validation.Validator will not have the validate(T) signature returning a Set like Jakarta Validator.

## 18. Configuring the Validation Provider and Messages

Spring Boot auto-configures validation when a compatible provider is on the classpath. In Spring Boot 3.5, **ValidationConfigurationCustomizer** is available to adjust provider configuration before creating the ValidatorFactory.

Example showing only the extension point:

~~~java
@Bean
ValidationConfigurationCustomizer validationCustomizer() {
    return configuration -> {
        // Add provider settings only when truly needed.
    };
}
~~~

This is an illustrative snippet, not a standalone runnable program. In Spring Boot 3.5, the import is typically:

~~~java
import org.springframework.boot.autoconfigure.validation.ValidationConfigurationCustomizer;
~~~

Spring Boot 4 moves the package under the validation module, for example:

~~~java
import org.springframework.boot.validation.autoconfigure.ValidationConfigurationCustomizer;
~~~

Use this only when you need to fine-tune provider-level behavior that cannot be solved via message bundles, annotations, or a simple Validator bean. A customizer can be ordered using Ordered/@Order if multiple beans configure it.

Do not manually define a @Bean LocalValidatorFactoryBean unless you intentionally need to customize it and understand the impact on MVC/WebFlux/service method validation. Replacing the global validator can alter endpoint behavior if the bean does not support Jakarta constraints properly.

## 19. Common Errors and Causes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| @Valid reports no errors | Missing provider, missing @Valid at integration point, or controller not using proper argument validation | Check validation starter and test with invalid input |
| Cannot import @NotBlank | Using javax instead of jakarta, missing starter/API | Check namespace and dependency tree |
| @NotNull does not reject "" | @NotNull only checks for null | Use @NotBlank if String must contain characters |
| @Email still accepts null | Format constraints usually treat null as valid | Combine with @NotBlank |
| @Min placed on String to check length | Misunderstanding constraint type | Use @Size or @Pattern |
| Nested DTO has errors but is not detected | Missing cascade @Valid on child field | Add @Valid and @NotNull when needed |
| Malformed JSON POST treated as validation error | Parse error happens before validation | Handle HttpMessageNotReadableException separately |
| HandlerMethodValidationException not caught by advice | Catching only MethodArgumentNotValidException | Add handling for method validation |
| @Validated service does not run | Self-invocation, instantiating bean with new, final/private method, or missing proxy | Call through Spring-managed proxy, check AOP |
| Validation group does not run | Constraint assigned to a group other than Default | Use @Validated(group) or adjust DTO/groups |
| One field produces multiple messages | Violated multiple constraints | Return a list or pick one message with a clear policy |
| Returning full rejectedValue in HTTP errors | Leaking user data | Return safe error codes/fields, do not echo sensitive data |
| 400 for every service error | Confusing input validation with server/business errors | Pick status based on error nature; 500/409/422 when appropriate |
| @Valid on DTO does not validate in batch process | No integration point | Call Validator.validate or method validation |
| Custom ConstraintValidator blocks WebFlux event loop | Blocking JDBC/HTTP call inside validation | Move business checks to an appropriate reactive service |

A quick checklist for an MVC controller:

1. Confirm the validation starter is in runtime dependencies.
2. Confirm jakarta.validation.* imports on Spring Boot 3+/4+.
3. Confirm the DTO has appropriate constraints.
4. Confirm the method argument has @Valid or @Validated appropriately.
5. Send a request with invalid data but syntactically valid JSON.
6. Observe the status and exception type.
7. Check whether @RestControllerAdvice handles the right error type.
8. Run MockMvc/WebTestClient across invalid, missing, and boundary cases.

## 20. Production Validation Design Checklist

- **Input:** Is there a dedicated input DTO instead of using a JPA entity directly?
- **Requiredness:** Are missing, null, empty, blank, and whitespace distinguished?
- **Data types:** Are wrappers or primitives used to detect missing fields?
- **Bounds:** Are string lengths, numeric ranges, email/ID formats, and collection sizes constrained?
- **Nested:** Is there cascade @Valid and @NotNull if the child object is required?
- **HTTP:** Is @Valid @RequestBody used, 400 tested, and sensitive data kept out of responses?
- **Method:** Is controller validation distinguished from @Validated service validation?
- **Groups:** Are Default vs custom groups clearly documented?
- **Security:** Are there business checks for permissions, authorization, rate limits, and ownership?
- **Database:** Are appropriate unique/check/foreign key constraints in place and conflicts/transactions handled?
- **Internationalization:** Are messages/locales consistent with the API contract?
- **Tests:** Are there tests for invalid, valid, boundary, malformed JSON, nested objects, and error responses?
- **Version:** Are Jakarta APIs and imports matching the Spring Boot version?
- **Operations:** Are metrics/logs free of passwords, emails, or raw payloads outside data policy?
- **Maintenance:** Avoid duplicating divergent constraints across HTTP, service, and persistence for the same invariant.

## 21. Self-Check Questions

1. How do Jakarta Validation and Hibernate Validator differ in role?
2. What does spring-boot-starter-validation provide, and why shouldn't you hardcode a Hibernate Validator version?
3. How do @NotNull, @NotEmpty, and @NotBlank handle the string "   "?
4. Why must @Email be combined with @NotBlank if the email is required?
5. Do you use @Size(min=3) or @Min(3) to limit String length?
6. When are constraints on a DTO executed in Spring MVC?
7. How do @Valid and @Validated differ?
8. Why does @Valid Address not reject address=null?
9. With Spring Framework 6.1+, what exception can an inline @Min on a controller @PathVariable trigger?
10. Why might a @Validated service not run if called via this.someMethod()?
11. Does a syntactically invalid JSON request always throw MethodArgumentNotValidException?
12. Should a service return HTTP 400 when a database unique constraint is violated?
13. What return type does Validator.validate produce?
14. Why might a constraint in the OnCreate group not run when using plain @Valid?
15. Does Spring Boot 3+ use javax.validation or jakarta.validation?

### Suggested Answers

1. Jakarta defines the standard API/annotations; Hibernate Validator is the implementation executing the constraints.
2. The starter provides compatible provider dependencies/infrastructure; letting the Boot BOM manage versions ensures compatibility.
3. @NotNull PASS, @NotEmpty PASS, @NotBlank FAIL.
4. @Email primarily validates format; it does not guarantee the field is provided and non-empty.
5. @Size(min=3), do not use @Min for String length.
6. When the framework receives the DTO at a supported integration point, such as @Valid @RequestBody, or when calling Validator directly.
7. @Valid is the Jakarta cascade/validation marker; @Validated is the Spring extension supporting groups/method validation.
8. @Valid only cascades when the child object exists; add @NotNull if required.
9. HandlerMethodValidationException with built-in method validation.
10. Self-invocation does not go through the regular Spring proxy.
11. No. JSON parse errors happen before Bean Validation and are reported via a different exception.
12. Errors must be expressed per the contract: duplicates may be 409 Conflict; do not automatically treat every database error as 400.
13. Set<ConstraintViolation<T>> from Jakarta Validator.
14. Because OnCreate does not automatically belong to the Default group; the appropriate group must be selected.
15. jakarta.validation.

## 22. Official References

- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html): enabling method validation when an implementation is present, @Validated on beans, and ValidationConfigurationCustomizer.
- [Spring Boot 4 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): validation starter and module/test starter changes.
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): LocalValidatorFactoryBean, Jakarta Validation integration, and custom constraints.
- [Spring Framework — MVC Controller Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): @Valid DTOs, built-in method validation, MethodArgumentNotValidException, and HandlerMethodValidationException.
- [Spring Framework — WebFlux Controller Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html): WebExchangeBindException and method validation in WebFlux.
- [Spring Framework — @RequestBody MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): deserialization and validation of request bodies.
- [Jakarta Validation Specification](https://jakarta.ee/specifications/bean-validation/): constraints, groups, cascade, validator, and constraint metadata.
- [Hibernate Validator Reference](https://docs.jboss.org/hibernate/stable/validator/reference/en-US/html_single/): built-in constraints, custom constraints, method validation, and interpolation.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): testing validation over HTTP with MVC.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing HTTP on the reactive stack.
