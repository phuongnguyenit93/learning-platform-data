# WebExchangeDataBinder, @InitBinder, and Custom Validators in Spring WebFlux

## 1. The problem and the goal

A WebFlux endpoint usually receives data from a query string, a form, multipart, or a JSON body. The application needs to convert these external values into Java types, check whether they have the correct format and business rules, and only then perform further processing.

Spring WebFlux provides related mechanisms that each have their own role:

- **WebExchangeDataBinder**: a binder specialized for the WebFlux environment; it takes query parameters, form data, and multipart data from the **ServerWebExchange** and puts them into the target object.
- **@InitBinder**: a binder configuration point for a controller or a group of controllers; it can register validators, converters, formatters, property editors, and restrict which fields may be bound.
- **org.springframework.validation.Validator**: an interface for writing custom data validation rules, independent of Jakarta Bean Validation.
- **@Valid / @Validated**: asks Spring to apply validation to the appropriate object or parameter.
- **BindingResult / Errors**: where binding errors, type conversion errors, and validation errors are held so the controller can handle them directly.

The common flow:

~~~text
HTTP request
    |
    v
Query / Form / Multipart values
    |
    v
WebExchangeDataBinder
    |
    +----> convert types and bind into the DTO
    |
    v
Bean Validation + custom Validator
    |
    v
BindingResult
    |
    +----> errors: return 400 / an appropriate message
    |
    +----> valid: call the reactive service
~~~

**Binding and validation are two different steps.** Binding answers the question "how are the request values put into the object?". Validation answers "is the object valid according to the rules after binding?". A value can bind successfully and still be invalid, for example an email that is the right type String but has the wrong format.

This lesson goes from the foundational API to @InitBinder configuration, writing a Validator, distinguishing forms from JSON, handling errors correctly in WebFlux, protecting against mass assignment, and testing with WebTestClient.

## 2. What is WebExchangeDataBinder?

**WebExchangeDataBinder** is in the **org.springframework.web.bind.support** package. It extends **WebDataBinder**, which extends **DataBinder**. It is a binder specialized for WebFlux requests, supporting binding from:

- Query parameters in the URL.
- Form data of type **application/x-www-form-urlencoded**.
- Multipart form data, including parts/files according to the supported mechanism.

Important APIs:

| API | Return type | Purpose |
| --- | --- | --- |
| **new WebExchangeDataBinder(target)** | WebExchangeDataBinder | Creates a binder for the target object |
| **new WebExchangeDataBinder(target, objectName)** | WebExchangeDataBinder | Creates a binder with an explicit object name |
| **bind(exchange)** | Mono<Void> | Binds query/form/multipart into the target reactively |
| **construct(exchange)** | Mono<Void> | Creates the target through constructor binding; available since Spring Framework 6.1 |
| **getValuesToBind(exchange)** | Mono<Map<String,Object>> | Gets the values that will be used for binding |
| **extractValuesToBind(exchange)** | Mono<Map<String,Object>> | Aggregates values from query/form/multipart |
| **getBindingResult()** | BindingResult | Gets the binding result and errors |
| **setAllowedFields(...)** | void | Allows binding only of the listed fields |
| **setDisallowedFields(...)** | void | Forbids binding of the listed fields |
| **addValidators(...)** | void | Adds validators to the binder |
| **validate(...)** | void | Runs the registered validators |

**bind(exchange) returns Mono<Void>** because reading a form or multipart can be asynchronous. Chain it into the pipeline with **then**, **map**, or **flatMap**; do not call block in the handler.

### 2.1. Creating a binder manually

An example illustrating a binder for a form:

~~~java
ProfileForm target = new ProfileForm();

WebExchangeDataBinder binder =
    new WebExchangeDataBinder(target, "profileForm");

binder.setAllowedFields("displayName", "email");
binder.addValidators(profileValidator);

return binder.bind(exchange)
    .then(Mono.fromSupplier(() -> {
        binder.validate();
        return binder.getBindingResult();
    }));
~~~

This is a snippet inside a method that has a **ServerWebExchange exchange**, with the type **ProfileForm** and **profileValidator** defined in the application. It does the following:

1. Creates a new target object for the current request.
2. Creates a WebExchangeDataBinder tied to the object name.
3. Allows binding of only the two defined fields.
4. Registers the custom validator.
5. Waits for binding to complete.
6. Runs validation and then gets the BindingResult.

When you create a binder yourself, the application must register the necessary validators itself. The snippet above registers only **profileValidator**; if you want to run Jakarta Bean Validation for annotations such as @NotBlank/@Email on the target, register the Spring Validator that corresponds to the Bean Validation provider, or use the @ModelAttribute/@Valid resolution path managed by the framework, as in the complete example in section 10.

**Each request must have its own binder and target.** Do not put a DataBinder/BindingResult in a singleton field, because they hold the target object and the error state of each binding.

### 2.2. Constructor binding in Spring Framework 6.1+

Since Spring Framework 6.1, WebExchangeDataBinder has an additional **construct(exchange)** to create the target through constructor binding from request values:

~~~java
WebExchangeDataBinder binder =
    new WebExchangeDataBinder(null, "profileForm");

return binder.construct(exchange)
    .then(Mono.fromSupplier(() -> {
        Object target = binder.getTarget();
        BindingResult result = binder.getBindingResult();
        return result.hasErrors() ? result : target;
    }));
~~~

This is an illustrative snippet; in a real application you should use a concrete target type instead of Object. After construct succeeds, you can call **bind(exchange)** to bind additional setter properties as needed. The constructor binding style suits immutable DTOs/records when the contract and constructor are clearly designed.

Do not assume every Spring version has construct(exchange). This API was added in **6.1**; if you use an older Framework, check the Javadoc for the exact version.

### 2.3. WebExchangeDataBinder is not a JSON decoder

An easily confused point:

| Data source | Commonly used mechanism |
| --- | --- |
| Query string | WebExchangeDataBinder / @ModelAttribute / @RequestParam |
| URL-encoded form | WebExchangeDataBinder / @ModelAttribute |
| Multipart form | WebExchangeDataBinder / @ModelAttribute / @RequestPart |
| JSON request body | HttpMessageReader and HTTP message codecs via @RequestBody |
| Validating an object after deserializing JSON | @Valid / @Validated and the corresponding Validator |

**A JSON body is decoded by a codec**, not put into the target by calling WebExchangeDataBinder.bind(exchange). You can use @Valid on @RequestBody so that Spring checks the object after deserialization.

## 3. Distinguishing binding, conversion, and validation

Three related tasks that do not replace each other:

1. **Binding:** takes the input values and puts them into the object's fields/properties/constructor.
2. **Conversion:** converts a value from a source type to a target type, for example the String "25" to the Integer 25, or a date string to LocalDate using a Converter/Formatter.
3. **Validation:** checks values/objects against rules, for example the name is not empty, the age is within limits, the email belongs to an accepted domain.

Example: a request sends age=abc. Conversion to Integer can fail; the error is recorded in the BindingResult. A request that sends age=-5 can be converted to an Integer successfully, but validation will report it as invalid.

| Situation | Binding/conversion | Validation |
| --- | --- | --- |
| age=25 | Succeeds | Can be valid |
| age=abc | Type conversion error | There is no valid value yet to check further |
| age=-5 | Succeeds | Error if there is @Min(0) |
| email=lan@example.com | Succeeds as a String | Can be valid |
| email=not-an-email | Succeeds as a String | Error if there is @Email |
| Missing required field | May bind null/empty | Error if there is @NotBlank/@NotNull |

**BindingResult** can contain both field errors and object errors. When you need to debug, read **getFieldErrors()**, **getGlobalErrors()**, and the error codes instead of just printing one general message.

## 4. What is @InitBinder used for?

**@InitBinder** marks a method that is called to configure the WebDataBinder before Spring binds data into a command object or prepares the appropriate conversion/validation.

Example:

~~~java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
    binder.addValidators(profileValidator);
}
~~~

The method usually receives a **WebDataBinder** and returns **void**. In WebFlux, the binder is actually created per request exchange and can be a **WebExchangeDataBinder**. We use the WebDataBinder type in the @InitBinder signature to work through the common abstraction.

### 4.1. Restricting by model attribute

You can apply it to only one specific model attribute:

~~~java
@InitBinder("signupForm")
void initSignupBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
}
~~~

When the binder is used for the model attribute named **signupForm**, this configuration is applied. If no name is passed in @InitBinder, the method may apply to the matching binders in the controller.

The name must match the declared model attribute:

~~~java
@ModelAttribute("signupForm") SignupForm form
~~~

### 4.2. Controller scope and @ControllerAdvice

- Put @InitBinder in a **@Controller** or **@RestController**: local configuration for that controller.
- Put @InitBinder in a **@ControllerAdvice**: can apply to many controllers.
- You can restrict @ControllerAdvice with **basePackages**, **assignableTypes**, or other suitable selectors to avoid affecting the entire application.

Example:

~~~java
@ControllerAdvice(basePackages = "com.example.publicapi")
public class PublicApiBindingAdvice {

    @InitBinder("signupForm")
    void initSignupForm(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "email");
    }
}
~~~

This is an illustrative snippet. Use a global advice only when the same rule truly applies to that group of controllers; otherwise, one endpoint's binder can accidentally affect another endpoint.

### 4.3. Commonly used customizations

~~~java
@InitBinder("signupForm")
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
    binder.setDisallowedFields("role", "admin", "accountStatus");
    binder.setAutoGrowCollectionLimit(64);
    binder.addValidators(signupValidator);
}
~~~

- **setAllowedFields** creates an allow-list of fields to bind.
- **setDisallowedFields** forbids some fields; an allow-list is usually easier to control for DTOs that receive external data.
- **setAutoGrowCollectionLimit** limits the automatic growth of collections/indexes when binding a property path.
- **addValidators** adds a validator; you should not use **setValidator** if the goal is to add without replacing the existing validator.
- **registerCustomEditor** registers a PropertyEditor for a specific type.
- **addCustomFormatter** registers a Formatter to parse/format a data type.
- **setRequiredFields** can declare required fields at the binding layer, but validation annotations usually express the rules more clearly for a DTO.

Not every endpoint needs all of the configuration above. Only set limits that fit the DTO and the API contract.

## 5. Writing a custom Validator

Spring provides the interface **org.springframework.validation.Validator**:

~~~java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
~~~

Two methods:

- **supports(clazz)** returns true if the validator understands that type of object.
- **validate(target, errors)** checks the object and records errors in Errors/BindingResult.

Example of a validator that checks the email domain:

~~~java
@Component
public class CompanyEmailValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return SignupForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;
        String email = form.getEmail();

        if (email != null
                && email.toLowerCase(Locale.ROOT)
                    .endsWith("@blocked.example")) {
            errors.rejectValue(
                "email",
                "email.domain.blocked",
                "This email domain is not accepted."
            );
        }
    }
}
~~~

This is a snippet that uses the **SignupForm** class from the example in section 10. **rejectValue** adds an error to the email field, with an error code and a default message.

### 5.1. Checking the class in supports

If supports returns false, Spring does not use that validator for the corresponding target. Use:

~~~java
return SignupForm.class.isAssignableFrom(clazz);
~~~

to support SignupForm and its subclasses. Do not return true for every class if the validate code below casts to a specific type.

### 5.2. rejectValue and reject

- **errors.rejectValue("email", ...)**: an error attached to a specific field, useful for showing the error next to the input.
- **errors.reject("signup.invalid", ...)**: an object-level error, not attached to a single field.

You can add multiple errors to the same object. You should not stop at the first error if the user can fix several fields at once and the API contract allows returning a list of errors.

### 5.3. Custom validators should be synchronous and fast

The Validator interface is a synchronous API. It suits purely data-based rules: checking relationships between fields, normalizing logic, formats, or local policies.

Do not call the database/network with block() inside a Validator to check whether an email already exists. That blocks the thread and brings blocking I/O into the binding step. For asynchronous checks, compose a reactive service after the object has been bound and has passed synchronous validation:

~~~java
return emailAvailability.isAvailable(form.getEmail())
    .flatMap(available -> {
        if (!available) {
            return Mono.error(
                new EmailAlreadyRegisteredException()
            );
        }
        return signupService.create(form);
    });
~~~

This is a snippet that needs the application's service and exception. The final uniqueness rule should still be protected by a unique constraint in the database, because two concurrent requests can both pass the check before writing.

## 6. How do Bean Validation and a custom Validator work together?

**Jakarta Bean Validation** uses annotations such as:

~~~java
@NotBlank
@Size(max = 80)
private String displayName;

@NotBlank
@Email
private String email;

@Min(18)
private int age;
~~~

Spring WebFlux can apply Bean Validation when the handler method uses **@Valid** or **@Validated** on an appropriate command object. If the binder already has a default validator from the Bean Validation provider, **binder.addValidators(customValidator)** lets you add a custom validator.

| Approach | Goal | Example |
| --- | --- | --- |
| Bean Validation | Declarative rules close to the field/class | @NotBlank, @Email, @Size, @Min |
| Spring Validator | Custom rules in Java | Checking the email domain, relationships between fields |
| Conversion/Formatter | Type conversion and formatting | String → LocalDate |
| Reactive business validation | Checks that need I/O | Email already exists, quota still sufficient |

**Do not replace the default validator by mistake.** **addValidators(...)** adds validators. **setValidator(...)** or **replaceValidators(...)** can replace the registered validators; use them only when you intentionally want to change the list.

### 6.1. @Valid and @Validated

- Jakarta Validation's **@Valid** triggers nested validation on the object.
- Spring's **@Validated** supports validation groups and some Spring ways of triggering validation.
- **@Valid is not itself a constraint annotation**; it asks for the constraints inside the object to be checked.
- A direct constraint such as **@NotNull** or **@Min** on a method parameter can trigger method validation at the handler method level.

Example:

~~~java
@PostMapping("/accounts")
public Mono<Account> create(
    @Valid @RequestBody Mono<Account> account
) {
    return account.flatMap(accountService::create);
}
~~~

WebFlux supports reactive request body arguments. The body is read and deserialized by an **HttpMessageReader/codec**, then the object is validated. This is a different flow from **WebExchangeDataBinder.bind(exchange)**, which is used for query/form/multipart.

## 7. Rules for handling validation errors in WebFlux

In Spring Framework 6.1+, you need to distinguish two kinds of exceptions.

### 7.1. WebExchangeBindException

When validation applies individually to a parameter such as @ModelAttribute, @RequestBody, or @RequestPart, if the parameter is an appropriate command object, there is no Errors/BindingResult right after it, and it does not fall under method validation, Spring can throw:

**WebExchangeBindException**

This exception contains a BindingResult, including field/object errors, for the application to turn into a response.

Example:

~~~java
@PostMapping("/accounts")
public Mono<Account> create(
    @Valid @RequestBody Account account
) {
    return accountService.create(account);
}
~~~

If Account is invalid, the handler method may not be called; the error is passed into WebFlux's exception handling. Normally this binding/validation error is mapped to **400 Bad Request**.

### 7.2. BindingResult or Errors right after the parameter

If you want to handle errors yourself in the handler:

~~~java
@PostMapping("/accounts")
public Mono<ResponseEntity<?>> create(
    @Valid @ModelAttribute("accountForm") AccountForm form,
    BindingResult bindingResult
) {
    if (bindingResult.hasErrors()) {
        return Mono.just(
            ResponseEntity.badRequest().body(bindingResult.getFieldErrors())
        );
    }

    return accountService.create(form)
        .map(account -> ResponseEntity.ok(account));
}
~~~

**BindingResult must come right after the parameter that needs to receive the errors.** When the error belongs to that parameter, Spring can call the method and supply the BindingResult so that the controller decides the response.

If another parameter in the same method has a validation error but has no Errors/BindingResult right after it, method validation can still raise an exception.

### 7.3. HandlerMethodValidationException

When there are direct constraints on a method parameter or return value, Spring can apply **method validation** to the entire handler method and raise:

**HandlerMethodValidationException**

Example:

~~~java
@GetMapping("/items")
public Mono<List<Item>> find(
    @RequestParam @Min(1) int page,
    @RequestParam @Max(100) int size
) {
    return itemService.find(page, size);
}
~~~

If page or size violates a constraint, the error belongs to method validation. This is a different mechanism from validation of an individual @ModelAttribute.

Spring Framework 6.1 has built-in method validation support for controllers. If a controller has a class-level **@Validated**, method validation can be performed through an AOP proxy. To use Spring Framework 6.1's built-in method validation for a controller, you need to remove the class-level @Validated as directed by the framework documentation.

### 7.4. Two exceptions to handle consistently

The application should have a policy for both:

- **WebExchangeBindException**: an error of one object/parameter binding.
- **HandlerMethodValidationException**: a validation error of parameters/return values at the method level.

You can handle them with **@ExceptionHandler** in a controller or **@ControllerAdvice**, or extend **ResponseEntityExceptionHandler** according to the API supported by the Spring version in use.

Do not return stack traces, internal class names, or sensitive raw rejected values to the client. Map them to stable error codes and messages.

## 8. @InitBinder with a custom Validator: configuration example

Suppose the signup form only allows the client to send **displayName** and **email**.

~~~java
@RestController
@RequestMapping("/api")
public class SignupController {

    private final CompanyEmailValidator emailValidator;

    public SignupController(CompanyEmailValidator emailValidator) {
        this.emailValidator = emailValidator;
    }

    @InitBinder("signupForm")
    void initSignupBinder(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "email");
        binder.addValidators(emailValidator);
    }

    // Handler methods...
}
~~~

Here:

- @InitBinder("signupForm") configures only the binder named signupForm.
- setAllowedFields creates the allow-list.
- addValidators adds the email domain rule.
- Bean Validation annotations on the DTO can still be enforced through the corresponding validator configured in WebFlux.

If you need to register a formatter:

~~~java
@InitBinder("signupForm")
void initSignupBinder(WebDataBinder binder) {
    binder.addCustomFormatter(new DateFormatter("yyyy-MM-dd"));
}
~~~

If a date/time type needs complex rules or an explicit timezone, consider using a **Converter** or **Formatter** managed by the ConversionService instead of parsing strings yourself in the controller.

### 8.1. Registering converters/formatters globally

If conversion is shared by many controllers, you can configure it through **WebFluxConfigurer** and the ConversionService instead of repeating @InitBinder in many places. Example of a Formatter for LocalDate:

~~~java
public class IsoDateFormatter implements Formatter<LocalDate> {

    private final DateTimeFormatter formatter =
        DateTimeFormatter.ISO_LOCAL_DATE;

    @Override
    public LocalDate parse(String text, Locale locale)
            throws ParseException {
        try {
            return LocalDate.parse(text, formatter);
        } catch (DateTimeParseException error) {
            ParseException exception =
                new ParseException("Expected yyyy-MM-dd", 0);
            exception.initCause(error);
            throw exception;
        }
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return formatter.format(value);
    }
}
~~~

This is a standalone snippet; register the Formatter through the WebFlux configuration or an appropriate binder. A Formatter should be stateless or safe for concurrent use. **DateTimeFormatter** is immutable and thread-safe.

## 9. Data binding security: avoiding mass assignment

Data binding can lead to vulnerabilities if the client can modify fields that are not allowed. For example, an internal entity has these properties:

~~~java
class AccountEntity {
    private String displayName;
    private String email;
    private boolean admin;
    private String status;
    private BigDecimal balance;
}
~~~

If the request is bound directly into the entity, the client can try to send:

~~~http
POST /accounts
Content-Type: application/x-www-form-urlencoded

displayName=Lan&email=lan@example.com&admin=true&balance=999999
~~~

If these properties are bound, the request can change permission state or sensitive data. This is the **mass assignment / over-posting** risk.

Mitigations:

1. **Use a dedicated request DTO** containing only the fields the client is allowed to modify.
2. **setAllowedFields(...)** to allow-list the fields to bind.
3. Do not use a persistence entity as the command object for a public request.
4. Do not trust role, admin, ownerId, balance, or status data sent by the client.
5. Check access permission on the object in the service/domain layer; a field binding validly does not mean the user has permission to modify that object.
6. Limit the depth/capacity of collection auto-grow if there are complex property paths.
7. Limit request size and multipart upload at the codec/server.
8. Check the BindingResult and suppressed fields if the business logic needs to detect that a client tried to send a forbidden field.
9. Use immutable DTOs/constructor binding when appropriate; avoid letting the client bind directly into a deep object graph.

### 9.1. Why is an allow-list better than only disallowing a few fields?

When an entity adds a new field, an old deny-list may not know about that new field. An allow-list by default only permits the fields that have been reviewed; a new field does not automatically become permitted input. This is a way to reduce risk as the model evolves.

**getSuppressedFields()** on the BindingResult can help detect fields blocked by the binder. However, you do not necessarily have to return the suppressed field details to the client; you can record a metric or log according to the security policy.

## 10. A runnable Java 17+ example: form binding, @InitBinder, and a custom Validator

The example uses Spring Boot 3.3.5, Spring Framework 6.1.x, and Java 17. It creates a signup endpoint that receives form-urlencoded data, combining Jakarta Bean Validation with a custom Validator to reject unaccepted email domains.

Structure:

~~~text
webflux-binding-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/binding/
    │   │       ├── BindingApplication.java
    │   │       ├── SignupForm.java
    │   │       ├── CompanyEmailValidator.java
    │   │       └── SignupController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/
            └── com/example/binding/
                └── SignupControllerTest.java
~~~

### 10.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webflux-binding-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
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

### 10.2. Application class

File **BindingApplication.java**:

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

### 10.3. DTO SignupForm

File **SignupForm.java**:

~~~java
package com.example.binding;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class SignupForm {

    @NotBlank(message = "Display name is required")
    @Size(max = 80, message = "Display name is too long")
    private String displayName;

    @NotBlank(message = "Email is required")
    @Email(message = "Email must be valid")
    private String email;

    public SignupForm() {
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

The DTO has only two fields that the client is allowed to enter. Do not add admin, role, balance, or internal fields to this command object.

### 10.4. Custom Validator

File **CompanyEmailValidator.java**:

~~~java
package com.example.binding;

import java.util.Locale;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public class CompanyEmailValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return SignupForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;
        String email = form.getEmail();

        if (email != null
                && email.toLowerCase(Locale.ROOT)
                    .endsWith("@blocked.example")) {
            errors.rejectValue(
                "email",
                "email.domain.blocked",
                "This email domain is not accepted"
            );
        }
    }
}
~~~

The Validator checks a rule that is not convenient to express with annotations alone: the **blocked.example** domain is not allowed. It does not access the database or network; validation remains a fast, synchronous operation.

### 10.5. Controller and @InitBinder

File **SignupController.java**:

~~~java
package com.example.binding;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import jakarta.validation.Valid;

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

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class SignupController {

    private final CompanyEmailValidator emailValidator;

    public SignupController(CompanyEmailValidator emailValidator) {
        this.emailValidator = emailValidator;
    }

    @InitBinder("signupForm")
    void initSignupBinder(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "email");
        binder.addValidators(emailValidator);
    }

    @PostMapping(
        value = "/signups",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public Mono<ResponseEntity<Map<String, Object>>> signup(
        @Valid @ModelAttribute("signupForm") SignupForm form,
        BindingResult bindingResult
    ) {
        if (bindingResult.hasErrors()) {
            List<Map<String, String>> errors =
                bindingResult.getFieldErrors().stream()
                    .map(this::toError)
                    .toList();

            Map<String, Object> body = new LinkedHashMap<>();
            body.put("errors", errors);

            return Mono.just(
                ResponseEntity.badRequest().body(body)
            );
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("message", "signup accepted");
        body.put("displayName", form.getDisplayName());
        body.put("email", form.getEmail());

        return Mono.just(
            ResponseEntity.accepted().body(body)
        );
    }

    private Map<String, String> toError(FieldError error) {
        Map<String, String> result = new LinkedHashMap<>();
        result.put("field", error.getField());
        result.put(
            "message",
            Objects.requireNonNullElse(
                error.getDefaultMessage(),
                "Invalid value"
            )
        );
        return result;
    }
}
~~~

Important points:

- **@InitBinder("signupForm")** applies to the model attribute named signupForm.
- **WebDataBinder** is the appropriate parameter type for the @InitBinder method; WebFlux uses an exchange-specific binder.
- **setAllowedFields** restricts the permitted input.
- **addValidators** adds CompanyEmailValidator.
- **@Valid** triggers Jakarta Bean Validation on the DTO.
- **BindingResult** stands immediately after SignupForm so the controller receives errors directly.
- The method still returns **Mono<ResponseEntity<...>>**, keeping response handling inside the reactive pipeline.

Without BindingResult immediately after the parameter needing validation, Spring can throw WebExchangeBindException when errors occur. Having BindingResult allows returning an error response according to the application's API format.

### 10.6. application.properties

~~~properties
spring.application.name=webflux-binding-demo
server.port=8080
logging.level.com.example.binding=INFO
~~~

### 10.7. Testing with WebTestClient

File **SignupControllerTest.java**:

~~~java
package com.example.binding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class SignupControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void acceptsValidForm() {
        client.post()
            .uri("/api/signups")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "displayName", "Lan"
            ).with("email", "lan@example.com"))
            .exchange()
            .expectStatus().isAccepted()
            .expectBody()
            .jsonPath("$.message").isEqualTo("signup accepted")
            .jsonPath("$.email").isEqualTo("lan@example.com");
    }

    @Test
    void rejectsBeanValidationErrors() {
        client.post()
            .uri("/api/signups")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "displayName", ""
            ).with("email", "not-an-email"))
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.errors").isArray();
    }

    @Test
    void rejectsCustomValidatorError() {
        client.post()
            .uri("/api/signups")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "displayName", "Lan"
            ).with("email", "lan@blocked.example"))
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.errors[0].field").isEqualTo("email")
            .jsonPath("$.errors[0].message")
                .isEqualTo("This email domain is not accepted");
    }
}
~~~

### 10.8. Running the application and testing

Requires JDK 17+ and Maven:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Send a valid form:

~~~bash
curl -i -X POST http://localhost:8080/api/signups \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=Lan" \
  --data-urlencode "email=lan@example.com"
~~~

Response body:

~~~json
{
  "message": "signup accepted",
  "displayName": "Lan",
  "email": "lan@example.com"
}
~~~

Send an email from a blocked domain:

~~~bash
curl -i -X POST http://localhost:8080/api/signups \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=Lan" \
  --data-urlencode "email=lan@blocked.example"
~~~

Response status **400 Bad Request**, illustrative body:

~~~json
{
  "errors": [
    {
      "field": "email",
      "message": "This email domain is not accepted"
    }
  ]
}
~~~

Send data failing Bean Validation:

~~~bash
curl -i -X POST http://localhost:8080/api/signups \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "displayName=" \
  --data-urlencode "email=not-an-email"
~~~

The response is **400 Bad Request** with a list of field errors. Error ordering can depend on the validator/provider; tests should only rely on defined fields and error codes/messages, not on the order of the entire list if ordering is not part of the contract.

Run tests:

~~~bash
mvn test
~~~

Three tests check: successful form binding, Bean Validation error, and custom Validator error. Spring Boot starts the server on a random port for the test.

## 11. Manual binder example with ServerWebExchange

In most controllers, Spring creates the binder and calls @InitBinder automatically. Only create **WebExchangeDataBinder** manually when you need to control the binding process in a special flow or when integrating below the controller layer.

Example of a method handling query/form:

~~~java
public Mono<BindingResult> bindProfile(
    ServerWebExchange exchange,
    ProfileValidator validator
) {
    ProfileForm target = new ProfileForm();

    WebExchangeDataBinder binder =
        new WebExchangeDataBinder(target, "profileForm");

    binder.setAllowedFields("displayName", "email");
    binder.addValidators(validator);

    return binder.bind(exchange)
        .then(Mono.fromSupplier(() -> {
            binder.validate();
            return binder.getBindingResult();
        }));
}
~~~

This is a snippet that only registers **ProfileValidator**. If the target also has Jakarta annotations such as @NotBlank, the manually created binder must have the appropriate Bean Validation Spring Validator added; the snippet does not automatically inherit @InitBinder from another controller.

You can inspect the result:

~~~java
return bindProfile(exchange, validator)
    .flatMap(result -> {
        if (result.hasErrors()) {
            return Mono.error(
                new InvalidProfileException(result)
            );
        }
        return profileService.save((ProfileForm) result.getTarget());
    });
~~~

This is a snippet assuming the exception and service. In a real application, the target type should be kept explicit instead of casting Object arbitrarily. Translating errors into a response can be placed in a handler or centralized exception handler.

### 11.1. Differences between bind and construct

- **bind(exchange)**: the target already exists; takes request values and assigns them to the target.
- **construct(exchange)**: the binder creates the target via constructor binding; this API is available since Spring Framework 6.1.
- You can **construct then bind** if you want to create an object from constructor arguments and then supplement some setter properties, but you must restrict fields and understand the processing order.

With immutable DTOs, constructor binding helps avoid objects in a half-initialized state. With JavaBean DTOs that have a no-arg constructor and setters, bind is the traditional, easy-to-understand approach.

## 12. JSON body and validation

For JSON, use @RequestBody so the codec reads the body into an object. Example:

~~~java
@PostMapping(
    value = "/json",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public Mono<ResponseEntity<String>> json(
    @Valid @RequestBody Mono<SignupJsonRequest> request
) {
    return request.map(value ->
        ResponseEntity.ok("accepted " + value.email())
    );
}
~~~

This is a snippet assuming **SignupJsonRequest** has Jakarta validation constraints. WebFlux supports reactive request-body arguments, so Mono<DTO> can be used. Deserialization is handled by **HttpMessageReader** and codecs; validation runs on the object that has been read.

If using a @RequestBody object directly instead of Mono:

~~~java
@PostMapping("/json")
public Mono<ResponseEntity<String>> json(
    @Valid @RequestBody SignupJsonRequest request
) {
    return Mono.just(ResponseEntity.ok("accepted"));
}
~~~

Both forms can be used in WebFlux; the Mono form fits when you want to compose clearly with the pipeline. **If declaring Errors/BindingResult to catch errors in the method, the request body should not be declared as Mono** per WebFlux's validation contract; the body needs to be resolved first so that BindingResult can stand immediately after the command object.

Do not use WebExchangeDataBinder.bind(exchange) to read a JSON body like a form. JSON is decoded by a codec, and body size limits are managed through the corresponding codec/server configuration.

## 13. Global Validator and local @InitBinder

There are two common configuration scopes:

| Scope | How to register | When to use |
| --- | --- | --- |
| Local | @InitBinder in the controller | Rules applying only to one controller or model attribute |
| Group of controllers | @ControllerAdvice + @InitBinder | Rules shared across a group of APIs |
| Application-wide | WebFluxConfigurer and global Validator | Rules/validators shared across many binders |
| DTO-specific | Bean Validation annotations and custom Spring Validator | Rules belonging to the DTO itself or data type |

A global validator can be configured via WebFlux config; multiple validators can be combined according to policy. If a validator is only meant for SignupForm, putting it in @InitBinder("signupForm") usually makes the scope easier to read.

Do not register a validator with type-specific casting logic for every object. Always implement **supports(...)** properly and consider scope.

## 14. Common mistakes and how to fix them

| Symptom / misconception | Correct understanding and fix |
| --- | --- |
| Using WebExchangeDataBinder to parse JSON | JSON uses HttpMessageReader/codecs via @RequestBody; the binder mainly handles query/form/multipart |
| Thinking binding means validation | Binding assigns/converts types; validation checks rules afterward |
| Calling binder.bind(exchange).block() | Bind is reactive; compose Mono<Void> with then/map/flatMap |
| Using a singleton DataBinder for all requests | The binder holds the target and BindingResult; create a new one per request |
| @InitBinder does not run | Check the model attribute name in @InitBinder("...") and the @ModelAttribute name |
| Custom Validator is not called | Check supports(clazz), binder scope, and whether addValidators was called |
| setValidator wipes out other validators | Use addValidators when you want to add |
| Validator calls the database with block | Validator is synchronous; move I/O checks to a reactive service after binding |
| No BindingResult immediately after @Valid parameter | Spring may throw WebExchangeBindException instead of invoking the method with errors |
| Handling WebExchangeBindException but ignoring method validation | Framework 6.1+ also has HandlerMethodValidationException |
| Putting @Valid on Map/Collection and expecting nested objects to always be validated like a command object | Individual parameter validation has conditions; check method validation and appropriate parameter types |
| Using @Valid without any constraints | @Valid only triggers nested validation; by itself it is not a constraint |
| Binding a JPA entity directly | Prone to mass assignment; use a request DTO and allow-list |
| Using only a deny-list for sensitive fields | New fields may accidentally be bound; an allow-list is safer |
| Not handling conversion errors | Wrong data types are recorded in BindingResult; return a clear error |
| Reading the body twice across resolvers | The body is a stream; design a single reading path and avoid competing consumers |
| Assuming @InitBinder automatically restricts entity edit permissions | The binder only restricts input; the service must still check authorization and business rules |
| Calling getFormData/getMultipartData without caring about body lifecycle | Form and multipart have their own parse/cache mechanism; do not read part content multiple times |
| Using constructor binding and forgetting to check the version | WebExchangeDataBinder.construct is available since Spring Framework 6.1 |
| Returning raw rejectedValue or internal exception messages | Can expose data; return controlled error codes and messages |

## 15. Binding and validation design checklist

Before deploying an endpoint, verify:

1. Does the request come from query, form, multipart, or JSON?
2. Is the right mechanism WebExchangeDataBinder/@ModelAttribute or codec/@RequestBody?
3. Does the DTO contain only the fields the client is allowed to send?
4. Is there a field allow-list via the binder if needed?
5. Does the Converter/Formatter handle formats and locales properly?
6. Does Bean Validation have the essential constraints?
7. Does the custom Validator have proper supports for the target and perform no blocking I/O?
8. Does @InitBinder have the right controller/model attribute scope?
9. Is BindingResult placed immediately after the parameter needing error handling?
10. Are both WebExchangeBindException and HandlerMethodValidationException covered by a handling policy?
11. Is asynchronous business validation composed in the reactive service?
12. Is authorization checked at the business layer, not relying solely on the binder?
13. Are there limits on payload, collection auto-grow, and multipart upload?
14. Are there tests for success, conversion error, bean validation error, custom validation, and blocked fields?
15. Does the error response have a stable structure and expose no sensitive data?

## 16. Practice exercises

**Exercise 1 — Query binding:** Create GET /api/search with @ModelAttribute SearchForm containing keyword and page. Use @InitBinder to allow only these two fields. Send a query string and inspect the target.

**Exercise 2 — Conversion:** Add LocalDate to the DTO, register a Formatter for the yyyy-MM-dd format. Try valid dates, nonexistent dates, and wrong formats.

**Exercise 3 — Custom Validator:** Create a validator checking that startDate must be before endDate. Use rejectValue for specific fields and reject for object-level errors.

**Exercise 4 — Validation groups:** Create Create and Update groups. Require email on create but not on update; use @Validated with the appropriate group.

**Exercise 5 — BindingResult:** Create an endpoint receiving @Valid @ModelAttribute and BindingResult immediately after. Verify the method is called when the form is invalid and returns a 400 response itself.

**Exercise 6 — WebExchangeBindException:** Remove BindingResult from the test endpoint, send invalid data, and handle the exception in @ControllerAdvice.

**Exercise 7 — Method validation:** Add @Min directly on a query parameter and observe HandlerMethodValidationException in Spring Framework 6.1+.

**Exercise 8 — Manual binder:** Create WebExchangeDataBinder with a new target, call bind(exchange), validate(), and read BindingResult. Compare with automatic @InitBinder.

**Exercise 9 — Security:** Create an internal entity with an admin field, send admin=true from the client. Ensure the DTO lacks this field and the binder only allows displayName/email.

**Exercise 10 — Reactive business rule:** After the DTO passes Bean Validation and the custom Validator, call a service checking email existence with Mono. Do not block in Validator; protect uniqueness with a database constraint.

**Exercise 11 — JSON:** Create @Valid @RequestBody Mono<SignupJsonRequest>, test malformed bodies and constraint-violating bodies. Distinguish deserialization errors from validation errors.

**Exercise 12 — Multipart:** Bind form metadata and file upload, limit size, and handle parts according to their lifecycle. Do not buffer large files into unbounded memory.

## 17. Key takeaways

**WebExchangeDataBinder** is a binder per ServerWebExchange, used for query/form/multipart and returning the bind result as a reactive Mono. **@InitBinder** configures the binder at controller or controller advice scope, including allow-lists, conversion, and validators. **Custom Validators** express domain rules where general annotations are not enough.

In WebFlux, distinguish binding/conversion from validation; use @Valid/@Validated on the right parameter types; place BindingResult immediately after the parameter if you want to handle errors in the method; prepare for both WebExchangeBindException and HandlerMethodValidationException. For JSON, use codecs via @RequestBody. For checks requiring I/O, keep them in the reactive service after synchronous validation.

Protect DTOs from mass assignment, create a separate binder per request, do not block, and test both valid data and possible errors.

## 18. References

- Spring Framework Reference — WebFlux Validation: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html
- Spring Framework Reference — WebFlux DataBinder / @InitBinder: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-initbinder.html
- Spring Framework API — WebExchangeDataBinder (6.1): https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/bind/support/WebExchangeDataBinder.html
- Spring Framework API — WebDataBinder: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/WebDataBinder.html
- Spring Framework API — Validator: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/Validator.html
- Spring Framework Reference — WebFlux @RequestBody: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework Reference — WebFlux Controller Method Arguments: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html
- Jakarta Bean Validation Specification: https://jakarta.ee/specifications/bean-validation/
