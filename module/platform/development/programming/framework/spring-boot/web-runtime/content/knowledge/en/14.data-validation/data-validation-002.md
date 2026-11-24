# @Valid, @Validated, and Validating Objects Received from HTTP in Spring Boot

An HTTP request can contain JSON, form fields, query parameters, path variables, or multipart content. **Being able to read a request does not mean the data is valid**: JSON may be syntactically valid yet have an empty name, an invalid email format, a negative age, or a nested address missing required fields. Spring Boot integrates Spring Validation and Jakarta Bean Validation to declare these constraints directly on data types and validate them at the HTTP boundary.

Two annotations to distinguish:

- **@Valid** belongs to the jakarta.validation.Valid package. It requests validation per Jakarta Validation, typically in the **Default group**, and allows validation to **cascade into nested objects** when placed on the corresponding field/property.
- **@Validated** belongs to the org.springframework.validation.annotation.Validated package. This is a Spring annotation supporting **validation groups**, used for objects in MVC/WebFlux and certain Spring method validation scenarios.

In Spring Framework 6.2, controllers also have **built-in method validation**: if a constraint such as @NotBlank or @Min is placed directly on a parameter of an @RequestMapping method, the framework can validate all parameters using its own mechanism. It is not identical to validating a @RequestBody DTO.

This lesson covers declaring constraints, nested validation, groups, HTTP outcomes, error handling, and testing. The full runnable example uses **Java 17+, Spring Boot 3.5.16, and Spring MVC**. The final sections distinguish differences in WebFlux and WebFlux.fn.

## 1. Three Layers to Understand: Binding, Validation, and Business Rules

Typical processing flow of a JSON request:

~~~text
HTTP POST /api/signups
    |
    | Content-Type: application/json
    v
Spring MVC HandlerMapping
    |
    v
HttpMessageConverter (Jackson)
    |
    v
JSON -> SignupRequest (Java record)
    |
    v
Bean Validation
  @NotBlank, @Email, @Min, @Valid ...
    |
    +-- Invalid -> HTTP 400 (default handling)
    |
    v
Controller -> application service
    |
    v
Business rules, persistence, authorization
    |
    v
HTTP response
~~~

**Binding/deserialization** turns HTTP data into Java objects. **Bean Validation** checks the constraints declared on objects. **Business validation** checks conditions that depend on system state or access permissions.

Examples:

- Syntactically invalid JSON: the parser cannot create the object -> usually 400, but this is **not** a @NotBlank error.
- Valid JSON with email="abc": the object is created, @Email detects the error -> usually 400.
- Well-formed email that is already registered: must query the database/service -> may be 409 Conflict per the API contract; do not assume @Email checks uniqueness.
- User tries to edit someone else's account: permission check -> usually 403; @Valid is not an authorization mechanism.

When observing a 400 response, distinguish parser errors, type conversion, missing parameters, validation, and business errors mapped to 400. Not every 400 originates from the same exception class.

## 2. Required Dependency and Import Namespace

With Spring Boot 3.5.x, to use Jakarta Bean Validation in a web app, add:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

This starter provides a compatible Bean Validation provider (usually Hibernate Validator) and Boot auto-configuration integration. Having only spring-boot-starter-web should not be assumed to guarantee a provider is present. Without a provider, writing annotations on a DTO does not guarantee requests will be validated.

Easily confused imports:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;
import org.springframework.validation.annotation.Validated;
~~~

For Spring Boot 3 / Spring Framework 6, use **jakarta.validation.***; do not copy old examples using javax.validation.*. The two namespaces come from different Java EE/Jakarta EE generations.

@Valid and @Validated do not always need to be placed side by side. Choose the annotation based on intent: @Valid for Default and cascade validation; @Validated when groups or applicable Spring method validation are needed.

## 3. Common Constraints and Null Behavior Differences

| Constraint | Typical Target | What It Checks | Common Misconception |
|---|---|---|---|
| @NotNull | Object, Integer, record component | Value is not null | Does not forbid empty strings or empty lists |
| @NotBlank | CharSequence | Non-null and contains at least one non-whitespace character | Suitable for required names and text codes |
| @NotEmpty | String, Collection, Map, array | Non-null and non-empty | A string containing only spaces is still non-empty |
| @Size(min,max) | String, Collection, Map, array | Length/element count | Typically accepts null; pair with @NotNull if required |
| @Email | String | Email syntax per provider | Does not verify mailbox exists; typically accepts null |
| @Pattern(regexp=...) | String | Regex for the value | Null is usually valid unless a required constraint is added |
| @Min/@Max | Supported numeric types | Numeric threshold | Null is usually valid; add @NotNull for required fields |
| @DecimalMin/@DecimalMax | Supported numeric types | Decimal threshold | Consider BigDecimal for monetary amounts |
| @Positive/@PositiveOrZero | Numbers | Positive / non-negative | Does not imply a value is present when null |
| @Past/@Future and variants | Supported date/time types | Time comparison | May depend on ClockProvider and timezone |
| @AssertTrue/@AssertFalse | Boolean | Boolean condition must be true/false | Null Boolean is usually valid unless @NotNull is added |
| @Valid | Object or collection elements | Triggers cascade validation | **Not a constraint**; does not prevent null |

Example:

~~~java
public record CreateUserRequest(
        @NotBlank String displayName,
        @NotBlank @Email String email,
        @NotNull @Min(18) Integer age,
        @Size(max = 120) String bio) {
}
~~~

Meaning:

- displayName cannot be null, "", or only whitespace.
- email must be non-blank and have an email format per the provider.
- age uses Integer to distinguish "value not sent" from 0. @NotNull catches missing; @Min(18) catches below 18.
- bio is allowed to be null, but if present, its length is limited to 120.

**Note on primitives:** if age is declared as int, it cannot hold null like Integer; when JSON omits age, a primitive default value or binding error may behave differently than intended. For input DTOs, use wrappers when missing/null must be distinguished.

**Note on email:** @Email does not guarantee the domain has a mailbox, that the email is unregistered, or that the address belongs to the user. Those steps require a dedicated verification flow.

## 4. When Does @Valid on @RequestBody Check the Object?

With Spring MVC:

~~~java
@PostMapping("/users")
public ResponseEntity<Void> create(
        @Valid @RequestBody CreateUserRequest request) {
    userService.create(request);
    return ResponseEntity.status(201).build();
}
~~~

This is an illustrative snippet, assuming CreateUserRequest and userService are already defined. @RequestBody asks Jackson/HttpMessageConverter to build the DTO. @Valid makes Spring apply Bean Validation to the bound DTO.

When no other method constraints require method validation, DTO errors normally produce **MethodArgumentNotValidException**; Spring MVC handles this by default as **HTTP 400 Bad Request**.

Cases that behave differently:

- **Empty request body** on an endpoint requiring @RequestBody (required=true by default): usually 400 due to missing body, before Bean Validation has a DTO to check.
- **Malformed JSON**: usually HttpMessageNotReadableException / 400; not MethodArgumentNotValidException.
- **Valid JSON but @NotBlank fails**: MethodArgumentNotValidException / 400 in standard argument validation flow.
- **Incompatible Content-Type** with consumes/converter: may return 415 Unsupported Media Type.
- **@RequestBody missing @Valid**: DTO may still deserialize successfully, but field constraints will not automatically trigger at this step.

With Spring Framework 6.1+, if a constraint like @NotBlank is declared directly on another parameter of the same controller method, the framework uses **built-in method validation**; in that case the exception may be HandlerMethodValidationException instead of MethodArgumentNotValidException. Therefore, error handlers should cover all validation types currently in use.

## 5. Cascade Validation: Nested Objects

HTTP DTOs often contain nested address, contacts, line items, or product info:

~~~java
public record AddressInput(
        @NotBlank String city,
        @NotBlank String postalCode) {
}

public record SignupInput(
        @NotBlank String displayName,
        @NotNull @Valid AddressInput address) {
}
~~~

Here:

- @NotNull on address forces the request to include an address object.
- @Valid on address allows validating constraints **inside AddressInput**.
- If @Valid is omitted, an empty city field may go unchecked when validating SignupInput.
- If @NotNull is omitted and address=null, @Valid alone does not treat null as an error.

Example body that should be rejected:

~~~json
{
  "displayName": "Lan",
  "address": {
    "city": "",
    "postalCode": "10000"
  }
}
~~~

When @Valid is placed properly on the nested field, the validator checks city and detects that @NotBlank fails.

### 5.1. Validation for Collection Elements

Bean Validation supports constraints on **type arguments**:

~~~java
public record BatchInput(
        @NotEmpty List<@NotBlank String> tags,
        @Valid List<AddressInput> addresses) {
}
~~~

- @NotEmpty requires tags to be non-null and have at least one element.
- List<@NotBlank String> checks each string in the list.
- @Valid List<AddressInput> requests cascading into each AddressInput when present.
- If the addresses list must be required and non-empty, add @NotEmpty to the collection itself.

This snippet illustrates Jakarta Validation 3.x on Java 17 and requires importing java.util.List along with the corresponding constraints.

Avoid using @Valid expecting a List to always have elements: @Valid only triggers cascading; element count is the responsibility of @NotEmpty or @Size.

## 6. How Does @Validated Differ from @Valid?

**@Valid** belongs to Jakarta Validation; the common case is running the **Default group** and cascade validation.

Spring's **@Validated** supports specifying validation groups, for example:

~~~java
@PostMapping("/premium")
public ResponseEntity<Void> premium(
        @Validated({Default.class, PremiumChecks.class})
        @RequestBody SignupRequest body) {
    return ResponseEntity.status(201).build();
}
~~~

This is an illustrative snippet before the full classes are defined in the project in section 8. In it:

- Default.class belongs to jakarta.validation.groups.Default.
- PremiumChecks.class is a **marker interface** declared by the application.
- @Validated({Default.class, PremiumChecks.class}) requests checking both default constraints and constraints in the PremiumChecks group.
- @Validated(PremiumChecks.class) **does not automatically include Default**. To validate both groups, specify both or design appropriate group inheritance/sequence.

### 6.1. Example Group-Based Constraint

~~~java
public interface PremiumChecks {
}

public record SignupRequest(
        @NotBlank String displayName,
        @NotBlank(groups = PremiumChecks.class)
        String inviteCode) {
}
~~~

With @Valid @RequestBody, by default displayName must be valid while inviteCode is not required under the default group. With @Validated({Default.class, PremiumChecks.class}) @RequestBody, both constraints are evaluated.

**Validation groups are a technique for selecting rule sets**, not a replacement for API versioning or permission checks. Do not create too many per-endpoint groups if it turns the DTO into a confusing set of conditions. Separate DTOs for Create/Update are often simpler if the two contracts differ significantly.

### 6.2. Group Sequences and Complex Constraints

Jakarta Validation supports @GroupSequence to control group evaluation order when a business contract truly requires it. However, if you only want to distinguish creation and update endpoints, start with separate DTOs or a few simple marker groups. Do not rely on error return ordering without an explicit group sequence; multiple constraint failures may be aggregated, and message order is not a stable contract.

## 7. Do Not Place @Validated on Controller Classes by Habit

In Spring Framework **6.1+**, Spring MVC and WebFlux have **built-in method validation** for handler methods. If you need constraints directly on controller parameters, for example:

~~~java
@GetMapping("/search")
public List<String> search(
        @RequestParam @NotBlank String keyword) {
    return List.of(keyword);
}
~~~

the framework can validate the keyword parameter **without @Validated on the controller class**. Invalid input normally produces **HandlerMethodValidationException** and maps to 400.

Placing @Validated at the class level can trigger the **AOP method validation** path instead of MVC's built-in mechanism. That causes the exception type, constraint evaluation point, and BindingResult handling to differ from expectations.

**Recommendation for controllers on Spring Framework 6.2:** use @Valid/@Validated on DTO parameters; place constraints directly on @RequestParam or @PathVariable when needed; **do not add @Validated to the controller class just to enable method validation**.

Distinguish this from **regular Spring services**: @Validated placed on a service class remains the standard way to enable Spring method validation via proxy for service methods, subject to AOP caveats around self-invocation. That is a different mechanism from built-in handler validation.

## 8. Runnable Sample Project with Java 17+ and Spring Boot 3.5

The project illustrates three scenarios:

1. POST /api/signups: @Valid checks Default constraints and the nested AddressInput object.
2. POST /api/signups/premium: @Validated selects Default + PremiumChecks, also requiring inviteCode.
3. GET /api/signups/search?keyword=...: @NotBlank directly on @RequestParam, using Spring MVC's built-in method validation.

Returned data is mocked, without writing to a database. Tests verify HTTP 201, 200, 400, and group validation.

### 8.1. Directory Structure

~~~text
validation-http-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/validation/
    │   │   ├── ValidationApplication.java
    │   │   ├── AddressInput.java
    │   │   ├── PremiumChecks.java
    │   │   ├── SignupRequest.java
    │   │   ├── SignupResponse.java
    │   │   └── SignupController.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/validation/
            └── SignupControllerTest.java
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>validation-http-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

This is a complete Maven file. The validation starter provides the Jakarta Validation provider, so annotations on records can actually be evaluated.

### 8.3. application.yml

~~~yaml
server:
  port: 8080

spring:
  application:
    name: validation-http-demo
~~~

You do not need to enable @EnableWebMvc or declare a custom Validator for default behavior. Spring MVC automatically uses the built-in validator when a provider is on the classpath and Boot auto-configuration applies.

### 8.4. ValidationApplication.java

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

The startup class is in the root package so component scanning finds the other controllers.

### 8.5. AddressInput.java

~~~java
package com.example.validation;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record AddressInput(
        @NotBlank(message = "city is required")
        String city,

        @NotBlank(message = "postalCode is required")
        @Pattern(
                regexp = "\\d{5}",
                message = "postalCode must have five digits")
        String postalCode) {
}
~~~

@Pattern allows null per the constraint contract; @NotBlank adds the requirement that a value must be present. The five-digit rule is only a **hypothetical demo rule**, not representative of all international addresses. Real projects need postal code rules based on country and API contract.

### 8.6. PremiumChecks.java

~~~java
package com.example.validation;

public interface PremiumChecks {
}
~~~

This empty interface is used solely as a **validation group marker**. It needs no implementation or Spring bean.

### 8.7. SignupRequest.java

~~~java
package com.example.validation;

import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record SignupRequest(
        @NotBlank(message = "displayName is required")
        @Size(max = 60)
        String displayName,

        @NotBlank(message = "email is required")
        @Email(message = "email format is invalid")
        String email,

        @NotNull(message = "age is required")
        @Min(value = 18, message = "age must be at least 18")
        Integer age,

        @NotNull(message = "address is required")
        @Valid
        AddressInput address,

        @NotEmpty(message = "interests must not be empty")
        List<@NotBlank String> interests,

        @NotBlank(
                groups = PremiumChecks.class,
                message = "inviteCode is required for premium")
        String inviteCode) {
}
~~~

Key points to observe:

- With @Valid, Default constraints require displayName, email, age, address, and interests.
- AddressInput is nested-validated because @Valid is placed on the address component.
- Elements of interests are checked via List<@NotBlank String>.
- inviteCode has a constraint belonging to **PremiumChecks**, which does not automatically activate in the Default group.
- inviteCode is allowed to be null in a standard request; however, the premium endpoint will require this field.

Do not use this DTO as a JPA entity or a place to hold user permissions. This object solely represents client-supplied data.

### 8.8. SignupResponse.java

~~~java
package com.example.validation;

public record SignupResponse(
        long id,
        String displayName,
        String tier) {
}
~~~

The response only contains fields the application intentionally exposes. It does not echo the entire request (including email, age, and inviteCode).

### 8.9. SignupController.java

~~~java
package com.example.validation;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.groups.Default;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/signups")
public class SignupController {

    @PostMapping
    public ResponseEntity<SignupResponse> standard(
            @Valid @RequestBody SignupRequest input) {

        SignupResponse body = new SignupResponse(
                1L, input.displayName().trim(), "STANDARD");

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(body);
    }

    @PostMapping("/premium")
    public ResponseEntity<SignupResponse> premium(
            @Validated({Default.class, PremiumChecks.class})
            @RequestBody SignupRequest input) {

        SignupResponse body = new SignupResponse(
                2L, input.displayName().trim(), "PREMIUM");

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(body);
    }

    @GetMapping("/search")
    public Map<String, String> search(
            @RequestParam @NotBlank String keyword) {

        return Map.of("keyword", keyword);
    }
}
~~~

**Important:** there is no @Validated on the SignupController class. Spring MVC 6.2 provides built-in handler method validation when it sees @NotBlank placed directly on keyword.

The controller only responds with mocked data. In production, call a service, handle persistence, and set a Location header for the newly created resource. Do not assume the demo creates real accounts.

### 8.10. Expected Requests

POST /api/signups with the following body will be valid **even without inviteCode**:

~~~json
{
  "displayName": "Lan",
  "email": "lan@example.com",
  "age": 22,
  "address": {
    "city": "Ha Noi",
    "postalCode": "10000"
  },
  "interests": ["java", "spring"]
}
~~~

Response HTTP 201, with a body like:

~~~json
{"id":1,"displayName":"Lan","tier":"STANDARD"}
~~~

If you send the exact body above to **POST /api/signups/premium**, the constraint in PremiumChecks detects the missing inviteCode and normally returns HTTP 400. To make it valid, add:

~~~json
"inviteCode": "PREMIUM-2026"
~~~

to the input JSON object (making sure commas are valid when adding the field). The premium response when valid is 201 with tier=PREMIUM.

GET /api/signups/search?keyword=spring returns 200 with body containing keyword="spring". GET /api/signups/search?keyword= containing only an empty string fails @NotBlank and is handled as HTTP 400.

## 9. Integration Testing with MockMvc

File **src/test/java/com/example/validation/SignupControllerTest.java**:

~~~java
package com.example.validation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SignupControllerTest {

    private static final String VALID_REQUEST = """
            {
              "displayName": "Lan",
              "email": "lan@example.com",
              "age": 22,
              "address": {
                "city": "Ha Noi",
                "postalCode": "10000"
              },
              "interests": ["java", "spring"]
            }
            """;

    @Autowired
    MockMvc mvc;

    @Test
    void standardAcceptsDefaultConstraints() throws Exception {
        mvc.perform(post("/api/signups")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(VALID_REQUEST))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.tier").value("STANDARD"))
                .andExpect(jsonPath("$.displayName").value("Lan"));
    }

    @Test
    void premiumRequiresGroupSpecificField() throws Exception {
        mvc.perform(post("/api/signups/premium")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(VALID_REQUEST))
                .andExpect(status().isBadRequest());
    }

    @Test
    void premiumAcceptsValidInviteCode() throws Exception {
        String premiumJson = """
                {
                  "displayName": "Lan",
                  "email": "lan@example.com",
                  "age": 22,
                  "address": {
                    "city": "Ha Noi",
                    "postalCode": "10000"
                  },
                  "interests": ["java", "spring"],
                  "inviteCode": "PREMIUM-2026"
                }
                """;

        mvc.perform(post("/api/signups/premium")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(premiumJson))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.tier").value("PREMIUM"));
    }

    @Test
    void invalidEmailIsRejected() throws Exception {
        mvc.perform(post("/api/signups")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(VALID_REQUEST.replace(
                            "lan@example.com", "not-an-email")))
                .andExpect(status().isBadRequest());
    }

    @Test
    void underageIsRejected() throws Exception {
        mvc.perform(post("/api/signups")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(VALID_REQUEST.replace(
                            "\"age\": 22", "\"age\": 16")))
                .andExpect(status().isBadRequest());
    }

    @Test
    void nestedCityIsValidated() throws Exception {
        mvc.perform(post("/api/signups")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(VALID_REQUEST.replace(
                            "Ha Noi", "")))
                .andExpect(status().isBadRequest());
    }

    @Test
    void blankCollectionElementIsRejected() throws Exception {
        mvc.perform(post("/api/signups")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(VALID_REQUEST.replace(
                            "\"spring\"", "\" \"")))
                .andExpect(status().isBadRequest());
    }

    @Test
    void directRequestParamConstraintReturns400() throws Exception {
        mvc.perform(get("/api/signups/search")
                    .param("keyword", " "))
                .andExpect(status().isBadRequest());
    }

    @Test
    void validSearchReturns200() throws Exception {
        mvc.perform(get("/api/signups/search")
                    .param("keyword", "spring"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.keyword").value("spring"));
    }

    @Test
    void malformedJsonIsRejectedBeforeBeanValidation()
            throws Exception {
        mvc.perform(post("/api/signups")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"displayName\":"))
                .andExpect(status().isBadRequest());
    }
}
~~~

The test suite distinguishes three important patterns: **Default DTO validation**, **group-specific validation**, and **method parameter validation**. It also checks nested objects and collection elements.

Run:

~~~bash
mvn test
mvn spring-boot:run
~~~

The tests do not depend on a database or external network. When successful, Maven returns exit code 0. Logs, random ports in CI environments, and test execution order are not fixed outputs.

**QA Note:** the HTTP example and classes above are built consistently for Spring Boot 3.5.16/Java 17; do not port directly to Boot 4 without checking test package and dependency API changes.

## 10. Testing Endpoints with curl

Run Spring Boot on port 8080:

~~~bash
curl -i -X POST "http://localhost:8080/api/signups" \
  -H "Content-Type: application/json" \
  --data '{
    "displayName":"Lan",
    "email":"lan@example.com",
    "age":22,
    "address":{"city":"Ha Noi","postalCode":"10000"},
    "interests":["java","spring"]
  }'
~~~

Expected result: HTTP 201, JSON body with tier=STANDARD.

Change the email to a non-email string:

~~~bash
curl -i -X POST "http://localhost:8080/api/signups" \
  -H "Content-Type: application/json" \
  --data '{
    "displayName":"Lan",
    "email":"invalid-email",
    "age":22,
    "address":{"city":"Ha Noi","postalCode":"10000"},
    "interests":["java"]
  }'
~~~

Expected result: HTTP 400; the exact error body depends on error handling and Problem Details configuration.

Test query parameter method validation:

~~~bash
curl -i "http://localhost:8080/api/signups/search?keyword=spring"
curl -i "http://localhost:8080/api/signups/search?keyword="
~~~

The first request returns 200, and the second returns 400. If you send a request omitting keyword **completely**, @RequestParam's default required=true may also return 400 for a missing parameter, which is a binding error distinct from a blank value violating @NotBlank.

These commands suit Unix shells; on Windows PowerShell, use curl.exe and adjust quoting as needed.

## 11. Two Validation Branches in Spring MVC 6.2

Spring Framework 6.2 distinguishes:

**Branch A — validating an object argument:** @ModelAttribute, @RequestBody, or @RequestPart marked with @Valid/@Validated, with no other method validation requirements and no Errors/BindingResult used to handle errors locally in the method. The error is typically **MethodArgumentNotValidException**.

**Branch B — method-level validation:** a constraint such as @NotBlank or @Min is placed directly on a controller parameter or return value. In that case, built-in method validation can also check nested DTO parameters via @Valid; input errors typically produce **HandlerMethodValidationException**, while return-value errors may carry a server error status.

| Controller Parameter Example | Expected Mechanism | Typical Error |
|---|---|---|
| @Valid @RequestBody SignupRequest body | Argument-level validation | MethodArgumentNotValidException / 400 |
| @Validated(Group.class) @RequestBody SignupRequest body | Group-based argument-level validation | MethodArgumentNotValidException / 400 |
| @RequestParam @NotBlank String keyword | Built-in method validation | HandlerMethodValidationException / 400 |
| @Valid @RequestBody DTO body **and** another parameter with @Min | Method validation may cover the whole method | HandlerMethodValidationException / 400 |
| @RequestBody DTO body with malformed JSON | Message converter cannot create DTO | HttpMessageNotReadableException / 400 |

**@Valid itself is not a constraint.** If you add @NotNull directly to a parameter that already has @Valid, the case may switch to method validation. Do not tweak annotations just to force an exception into an existing handler; design handlers to support the actual error types.

### 11.1. What About Class-Level @Validated on a Controller?

In Spring Framework 6.1+, class-level @Validated can cause method validation to run through an AOP proxy. When using built-in controller method validation, Spring recommends removing class-level @Validated to leverage the built-in mechanism. The AOP path may throw ConstraintViolationException or MethodValidationException depending on configuration; do not assume it is always HandlerMethodValidationException.

This is a common pitfall when upgrading from Spring 5/Boot 2: legacy code that habitually placed @Validated on controller classes may need adjustment to unify error handling in newer generations.

## 12. BindingResult and Handling Errors Directly in the Controller

If you want the controller to handle validation errors instead of throwing an exception to a global handler, place **BindingResult or Errors immediately after the validated parameter**:

~~~java
@PostMapping("/manual-check")
public ResponseEntity<?> create(
        @Valid @RequestBody SignupRequest request,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return ResponseEntity.badRequest().body(
                Map.of("message", "invalid request"));
    }

    return ResponseEntity.status(201).build();
}
~~~

This is a standalone illustrative snippet requiring imports for BindingResult, ResponseEntity, Map, the corresponding annotations, and SignupRequest; it is not part of the sample SignupController. Important conditions:

1. BindingResult must stand **immediately after** the @Valid/@Validated parameter it handles.
2. Without an appropriate BindingResult, validation errors normally go through exception handling.
3. If the method has constraints directly on other parameters and built-in method validation applies, there are cases where the controller is still not invoked because an error belongs to a parameter without a corresponding Errors/BindingResult.
4. Avoid both handling errors inside every controller and adding a duplicate global handler that causes the API to return inconsistent formats.

For multi-endpoint APIs, **@RestControllerAdvice** is usually easier to standardize; for forms that need to display validation errors directly in a view, BindingResult is the right tool.

## 13. Designing a Consistent Error Response

When a request is invalid, the API needs to clearly report which field failed without leaking unnecessary data. Spring supports **ProblemDetail** per RFC 9457 and error response mechanisms. You can intentionally create a custom schema with an error code, field, message, and request identifier.

Illustrative **design** response, not an immutable default JSON from Spring Boot:

~~~json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "One or more fields are invalid",
  "invalidFields": [
    {
      "field": "email",
      "message": "email format is invalid"
    },
    {
      "field": "address.city",
      "message": "city is required"
    }
  ]
}
~~~

Notes:

- **MethodArgumentNotValidException** contains BindingResult/FieldError to extract fields and messages.
- **HandlerMethodValidationException** represents validation results across multiple method parameters; do not simply force it into a single FieldError.
- **ConstraintViolationException** typically appears when Jakarta method validation runs through AOP or Validator is called manually; do not automatically assume it is always an HTTP client error, as internal invariant violations can occur.
- **WebExchangeBindException** belongs to WebFlux; do not import it into a Spring MVC handler just because both check @Valid.
- The error body should not include rejectedValue if it is a password, access token, secret, or sensitive data.

When writing @RestControllerAdvice, use ResponseEntityExceptionHandler or specific @ExceptionHandler methods matching your version, and avoid catching generic Exception and turning every server error into HTTP 400.

### 13.1. Do Not Turn Return-Value Validation into 400

If output generated by the server violates a constraint (e.g., a controller/service returns invalid data), that is not necessarily the caller's fault. Spring Framework can use **500** for controller method return-value constraint violations. Returning 400 in this case skews monitoring and misattributes blame.

## 14. @ModelAttribute: Data from Query/Form

In Spring MVC, forms or query parameters are often bound into an object via @ModelAttribute:

~~~java
public class SearchForm {

    @NotBlank
    private String keyword;

    @Min(1)
    private int page = 1;

    public String getKeyword() {
        return keyword;
    }

    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }

    public int getPage() {
        return page;
    }

    public void setPage(int page) {
        this.page = page;
    }
}
~~~

This illustrative snippet requires importing jakarta.validation.constraints.NotBlank and Min. Corresponding endpoint:

~~~java
@GetMapping("/search-form")
public List<String> search(
        @Valid @ModelAttribute SearchForm form) {
    return List.of(form.getKeyword());
}
~~~

Do not place this snippet in the section 8 project without adding the class and imports. It demonstrates that validation is not restricted to JSON.

**Difference:** @RequestBody uses HttpMessageConverter to read the entire body; @ModelAttribute binds from request parameters/form fields via WebDataBinder. With multipart/form-data, you can use @RequestPart for a JSON DTO or @ModelAttribute for form fields depending on architecture.

Regarding file uploads:

- FilePart is the reactive WebFlux type; MultipartFile is normally used in Servlet MVC.
- Validation annotations on metadata DTOs can check text fields, while file size, MIME type, file content, and malware scanning require additional work.
- Do not store or serve files using client-supplied filenames without checking paths, access permissions, and safe storage practices.

## 15. Validation Groups: Create, Update, and Impact on the Default Group

A common scenario:

- On creation, password is required.
- On profile update, password is optional.
- On premium account creation, inviteCode is required.

Groups can be used:

~~~java
public interface CreateChecks {
}

public interface UpdateChecks {
}

public record ProfileInput(
        @NotBlank(
                groups = {CreateChecks.class, UpdateChecks.class})
        String displayName,

        @NotBlank(groups = CreateChecks.class)
        String password) {
}
~~~

When an endpoint uses @Validated(CreateChecks.class), it validates displayName and password. When it uses @Validated(UpdateChecks.class), only displayName requires @NotBlank.

However:

- Constraints without declared groups belong to the Default group.
- Running @Validated(CreateChecks.class) does not automatically run constraints in the Default group.
- For types with completely different requirements between create and update, two separate DTOs are clearer.
- Group sequences/inheritance can make behavior subtle; write tests for each group used by the public API.

If a single DTO has so many groups that it becomes hard to tell which fields are required at which endpoint, revisit the input contract design.

## 16. Custom Constraints When Standard Annotations Are Not Enough

There are situations requiring rules like "registration code must start with ACCT-" or checking relationships between two fields. Standard constraints cannot describe every business format.

A Jakarta Validation style custom constraint usually consists of:

1. An annotation declaring @Constraint, message, groups, and payload.
2. A ConstraintValidator<A,T> defining isValid.
3. Registering or letting the provider discover the validator via the annotation.
4. Testing valid, empty, malformed data, and boundary cases.

Example standalone annotation and validator for String:

**AccountCode.java**

~~~java
package com.example.validation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Target({ElementType.FIELD, ElementType.PARAMETER,
         ElementType.RECORD_COMPONENT})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = AccountCodeValidator.class)
public @interface AccountCode {

    String message() default "account code must start with ACCT-";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

**AccountCodeValidator.java**

~~~java
package com.example.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class AccountCodeValidator
        implements ConstraintValidator<AccountCode, String> {

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {

        return value == null || value.matches("ACCT-[A-Z0-9]{4}");
    }
}
~~~

This is a **standalone extension, not yet applied to SignupRequest in the sample project**. To use it, add both classes to the same package and place @AccountCode on an appropriate String field, combined with @NotBlank if the field is required.

The validator returns true for null because the "required" responsibility should be checked separately by @NotBlank/@NotNull; this keeps constraints decoupled and reusable.

**Do not put slow database queries or synchronous HTTP calls inside ConstraintValidator.isValid** to check uniqueness per request when avoidable. Doing so makes validation resource-heavy, hard to manage around transactions/timeouts, and still vulnerable to race conditions. Uniqueness invariants must be enforced at the database/service layer, not just in a validation annotation.

## 17. Service Method Validation Differs from Controller Validation

Beyond the HTTP boundary, Spring can validate service methods:

~~~java
@Service
@Validated
public class RegistrationService {

    public void reserve(@NotBlank String email) {
        // Business logic.
    }
}
~~~

This is an illustrative snippet. For Spring method validation via proxy, Spring Boot can auto-register the appropriate infrastructure when a Bean Validation provider exists. Depending on configuration, violations may produce ConstraintViolationException or MethodValidationException.

Note **self-invocation**: when one method in the same object calls another method of itself, the call can bypass the Spring AOP proxy so service-level validation does not run as expected. Tests should call through the Spring-managed bean/proxy.

HTTP validation does not replace service validation when the service is called from scheduled jobs, message listeners, or other tests. Conversely, service method validation does not guarantee the API response has a clean error schema: input-attributable errors must be mapped to 4xx while system invariants remain 5xx when appropriate.

## 18. Spring WebFlux and Reactive Validation

Spring WebFlux annotated controllers also support @Valid/@Validated with Jakarta Bean Validation, but run on the reactive stack.

Illustrative example:

~~~java
@PostMapping("/reactive-signups")
public Mono<SignupResponse> register(
        @Valid @RequestBody Mono<SignupRequest> body) {

    return body.map(input ->
            new SignupResponse(
                    1L, input.displayName(), "STANDARD"));
}
~~~

This snippet requires importing Mono, WebFlux/controller annotations, and the corresponding DTO; it is not part of the sample Spring MVC project. Spring WebFlux decodes the reactive body before validating per the framework's validation rules.

Common error types:

| Case | Spring MVC | Spring WebFlux |
|---|---|---|
| @Valid/@Validated on a @RequestBody object | MethodArgumentNotValidException | WebExchangeBindException |
| Direct constraint on handler method param | HandlerMethodValidationException | HandlerMethodValidationException |
| Malformed JSON body | HttpMessageNotReadableException and read error family | ServerWebInputException or corresponding decode error |
| Service method via AOP @Validated | ConstraintViolationException or MethodValidationException per config | Similar for AOP, but reactive return types and validation mechanics must be considered |

Do not call block() in a reactive controller just to validate a DTO. HTTP-layer validation should happen through mechanisms compatible with the reactive pipeline. For business checks requiring I/O, use appropriate publishers/schedulers and map errors clearly.

### 18.1. WebFlux.fn and RouterFunction

Functional endpoints receive ServerRequest and return Mono<ServerResponse>, such as request.bodyToMono(SignupRequest.class). There is no controller method carrying @Valid @RequestBody for the framework to handle automatically like an annotated controller.

A functional handler usually needs to invoke Validator explicitly:

~~~java
public Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(SignupRequest.class)
            .flatMap(input -> {
                Set<ConstraintViolation<SignupRequest>> errors =
                        validator.validate(input);

                if (!errors.isEmpty()) {
                    return ServerResponse.badRequest().build();
                }

                return ServerResponse.ok()
                        .bodyValue(input.displayName());
            });
}
~~~

The snippet above is **illustrative inside a handler class with an injected validator**, not a standalone Java file; it requires importing ServerRequest, ServerResponse, Set, ConstraintViolation, and the DTO type. With WebFlux.fn, do not assume validation is automatically enabled just because the DTO has @NotBlank. For group-specific checks, call validator.validate(input, PremiumChecks.class) or the needed groups and map the response yourself.

If validation requires a blocking database call, do not perform it directly on the event loop; design a reactive service or isolate blocking work properly. Standard Bean Validation should prioritize fast, CPU-only checks.

## 19. Internationalizing Validation Messages

Each constraint has a message; for example:

~~~java
@NotBlank(message = "{signup.displayName.required}")
String displayName
~~~

You can create **src/main/resources/messages.properties**:

~~~properties
signup.displayName.required=Display name is required
~~~

and **src/main/resources/messages_vi.properties**:

~~~properties
signup.displayName.required=Ten hien thi la bat buoc
~~~

This illustrates message bundles; depending on MessageSource and Hibernate Validator configuration, interpolating validation messages with Spring MessageSource may need verification in integration tests. If you want accented Vietnamese support, save resource files in UTF-8 according to project settings.

Output data should be designed stably: clients may need a language-independent **error code** while the message is localized. Do not use text messages as business identifiers because translations can change.

## 20. Security When Accepting Data from HTTP

Validation helps reduce data errors, **but it is not a complete security tool**.

- **Mass assignment:** do not bind request JSON directly into a JPA entity containing fields like role, ownerId, isAdmin, or internalStatus. Use a public DTO containing only fields the client is allowed to set.
- **Authorization:** @Valid does not check whether the sender has permission to update a resource; use a security layer/service.
- **Uniqueness/race conditions:** a validator checking that an email does not exist does not guarantee uniqueness if two requests run concurrently; use a database uniqueness constraint.
- **Sensitive error data:** do not include rejectedValue of passwords/tokens in ProblemDetail or logs.
- **Body size:** validation only runs after the framework reads/decodes the body; very large requests need proper HTTP body/multipart limits.
- **Regex DoS:** overly complex patterns or unbounded input can create performance risks; limit lengths and keep regexes simple.
- **Normalization:** trim/case-fold data per domain rules consistently before or after validation; @NotBlank does not turn "  Lan  " into "Lan".
- **Secrets in DTO:** do not serialize the entire input back into the response, even when validation succeeds.
- **JSON unknown fields:** whether unknown fields are permitted is a Jackson/ObjectMapper decision, separate from Jakarta Validation; strict mapping may be needed depending on the contract.

If input needs cross-field rules (e.g., startDate <= endDate), you can write a class-level constraint or validate in the service; do not encode an entire domain's business rules into a massive number of hard-to-maintain annotations.

## 21. Common Errors and How to Handle Them

| Symptom | Likely Cause | Resolution |
|---|---|---|
| @NotBlank on DTO does not block HTTP request | Missing @Valid/@Validated on @RequestBody or missing validation provider | Add spring-boot-starter-validation and place the annotation properly on the parameter |
| Import javax.validation.* does not compile | Project uses Boot 3 / Jakarta namespace | Switch to jakarta.validation.* |
| @Valid on address but address=null still passes | @Valid does not reject null by itself | Add @NotNull |
| @Email accepts email=null | @Email only checks format when a value is present | Combine with @NotBlank |
| @Min on Integer still accepts null | @Min usually allows null | Combine with @NotNull |
| @Validated(CreateChecks.class) skips default @NotBlank | CreateChecks group does not automatically include Default | Specify Default too or design group inheritance |
| Premium POST does not require inviteCode | Using @Valid Default group instead of @Validated PremiumChecks | Set groups properly and write tests |
| @Validated on controller class gives unexpected exception | Spring AOP method validation replaces built-in handler validation | Review class-level @Validated; handle the right exception type |
| @RequestParam @NotBlank is not checked | Different framework version/config or missing provider | Check Boot/Framework version and method validation integration |
| Malformed JSON does not hit @ExceptionHandler(MethodArgumentNotValidException) | Parser fails before validation | Handle HttpMessageNotReadableException separately |
| BindingResult does not receive errors | Not placed immediately after @Valid parameter, or other method validation applies | Fix method signature and review handler method validation rules |
| Nested list has blank element without error | Missing container element constraint or corresponding cascade | Use List<@NotBlank String>, @Valid for object elements |
| Error body returns full request/password | Error serializer/log includes rejectedValue | Output only field name, error code, and safe message |
| Custom constraint has slow database call | Validation contains uncontrolled I/O | Move to service, timeouts, and DB constraints |
| WebFlux.fn does not run @Valid like annotated endpoint | Functional handler has no equivalent automatic argument validation | Inject Validator and call validate explicitly |
| Return-value error labeled 400 | Overly broad global error advice | Distinguish input errors from server-side invariants |
| Valid POST data creates duplicate accounts | Bean Validation does not replace uniqueness | Use service transactions + database unique index |

## 22. Testing and Review Checklist

- [ ] Correct Java/Spring Boot version and jakarta.validation.* namespace.
- [ ] Bean Validation provider present, usually via spring-boot-starter-validation.
- [ ] Every HTTP DTO needing validation has @Valid or @Validated at the binding point.
- [ ] Required fields have appropriate @NotBlank/@NotNull/@NotEmpty.
- [ ] For nullable wrappers, null and range constraints are declared separately when needed.
- [ ] For nested objects, @Valid is on the containing field/component, plus a required constraint if null is invalid.
- [ ] For collections, constraints exist on both the collection and its elements when needed.
- [ ] Validation groups are explicitly specified; the Default group is not accidentally skipped.
- [ ] Do not place @Validated on the controller class just to get built-in method validation.
- [ ] Tests exist for @Valid @RequestBody, @Validated groups, and direct @RequestParam constraints.
- [ ] JSON parsing, Content-Type, validation, and business rule errors are distinguished.
- [ ] Stable response schema for input errors without exposing sensitive values.
- [ ] Do not rely on a single HTTP controller as the sole validation point if the service is also called from jobs/message listeners.
- [ ] Tests exist for missing, blank, null, min/max boundaries, invalid formats, nested objects, and collection items.
- [ ] Compatibility verified for Spring MVC/Servlet or WebFlux/reactive respectively.

## 23. Conclusion

**@Valid** is suited for default validation of a DTO received from HTTP and for nested checks. **@Validated** is suited when selecting validation groups or enabling Spring's method validation mechanism on appropriate beans. With Spring MVC 6.2, understanding the difference between **argument-level validation** and **built-in method validation** is essential to properly handle MethodArgumentNotValidException and HandlerMethodValidationException.

The reliable path is: define minimal input DTOs → declare constraints → place @Valid/@Validated properly on HTTP parameters → test valid/invalid requests → standardize error responses → additionally enforce business rules, authorization, and database invariants. Do not confuse successful JSON deserialization with valid data, and do not use Bean Validation to replace all business logic.

## Official Documentation

- [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — Bean Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — WebFlux Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html)
- [Jakarta Validation — Specification](https://jakarta.ee/specifications/bean-validation/)
- [Spring Boot 3.5 — Reference Documentation](https://docs.spring.io/spring-boot/3.5/reference/)
