# Applying Explicit Validation in Handlers

**Module:** Spring Framework – reactive  
**Parent topic:** Functional endpoints

## Learning Objectives

After this lesson, you can:

1. Explain why a WebFlux functional endpoint needs to explicitly invoke a validator after decoding the request body into an object.
2. Use `org.springframework.validation.Validator`, `SmartValidator`, `Errors`, and `BeanPropertyBindingResult` to validate a DTO directly inside a `HandlerFunction`.
3. Distinguish data validation from JSON deserialization, request parameter binding, and business rule checks requiring I/O.
4. Return a structured HTTP 400 or throw `ServerWebInputException` for WebFlux to handle input errors.
5. Integrate Jakarta Bean Validation via `LocalValidatorFactoryBean`, using constraints, cascading, and validation groups in a handler.
6. Keep the pipeline reactive without `block()`, nested `subscribe()`, or synchronous database queries inside validators.
7. Test valid requests, constraint-violating requests, empty bodies, and malformed JSON using `WebTestClient`.

## 1. Why Must Functional Endpoints Invoke Validators Explicitly?

WebFlux has two common programming models: annotated controllers with `@RestController`/`@RequestBody`, and functional endpoints with `RouterFunction`/`HandlerFunction`. With functional endpoints, the application writes a function that takes a `ServerRequest` and returns a `Mono<ServerResponse>`.

When reading a JSON body, `ServerRequest.bodyToMono(CreateProductRequest.class)` only asks the message reader/codec to decode the body into an object. It does not automatically infer all business rules from annotations on the DTO and invoke validation like the argument validation mechanism of annotated controllers.

Therefore, the handler needs to call the validator after obtaining the object:

```text
HTTP JSON bytes
      |
      v
request.bodyToMono(CreateProductRequest.class)
      |
      v
Jackson / HttpMessageReader deserialize
      |
      v
CreateProductRequest
      |
      v
Validator.validate(object, errors)
      |
      +---- empty errors ----> reactive service ----> ServerResponse 2xx
      |
      +---- has errors ------> ServerResponse 400
```

**This order is critical:** only validate the object after decoding succeeds. Syntactically invalid JSON or values that cannot be converted into Java types will emit an error from the codec before the handler has a DTO to check. Validation does not fix JSON and does not replace the deserialization process.

In an annotated controller, Spring can automatically trigger validation on a command object via `@Valid`/`@Validated` on a method argument. In WebFlux.fn, placing `@Valid` on a variable or DTO does not automatically invoke a validator. The handler itself must perform the validation step explicitly.

## 2. Three Concepts to Keep Separate

| Task | Question to answer | Commonly used API |
| --- | --- | --- |
| Deserialize | Can the JSON be converted into the expected Java type? | `request.bodyToMono(Type.class)`, HttpMessageReader/codec |
| Validate DTO | Does the created object satisfy the constraints? | `Validator.validate(object, errors)` or Jakarta `Validator.validate(object)` |
| I/O-dependent business checks | Does the SKU already exist in the database? Does the user have permission to create the record? | Reactive service/repository using `Mono`/`Flux` |

Example:

- `"price": "many"` when Java expects `BigDecimal` is a deserialization error.
- `"price": -5` can deserialize successfully but violates the positive price rule.
- A positive price whose SKU already exists is a business error requiring a persistence-layer query.

Do not lump these three error types into a single synchronous validator. Keeping them separate helps choose the right HTTP status, message, and handling approach.

## 3. Spring Validator and BeanPropertyBindingResult

Spring provides the `org.springframework.validation.Validator` interface:

```java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
```

- `supports(clazz)` indicates whether the validator handles that object type.
- `validate(target, errors)` checks the object and records errors into `Errors`.
- `Errors`/`BindingResult` stores field-level or object-level errors.
- `BeanPropertyBindingResult` creates an error container bound to an object, supporting property names like `name` or `address.city`.

Core pattern in a handler:

```java
Errors errors = new BeanPropertyBindingResult(requestDto, "requestDto");
validator.validate(requestDto, errors);

if (errors.hasErrors()) {
    // Create HTTP 400 or throw an input error.
}
```

`BeanPropertyBindingResult` requires an object whose properties can be accessed according to JavaBean property conventions. In the examples below, the DTO uses getters/setters for stable binding and field error retrieval.

### 3.1. Creating a custom Spring Validator

Example validator for a create-product request:

```java
@Component
public class CreateProductValidator implements Validator {
    @Override
    public boolean supports(Class<?> clazz) {
        return CreateProductRequest.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        CreateProductRequest request = (CreateProductRequest) target;

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "name", "name.required", "name is required");

        if (request.getPrice() == null) {
            errors.rejectValue(
                    "price", "price.required", "price is required");
        } else if (request.getPrice().signum() <= 0) {
            errors.rejectValue(
                    "price", "price.positive",
                    "price must be greater than zero");
        }
    }
}
```

This is an **illustrative snippet**, assuming `CreateProductRequest` has `getName()` and `getPrice()` getters. `ValidationUtils.rejectIfEmptyOrWhitespace` is a handy helper for required strings. `errors.rejectValue` records an error on the exact field; the handler can retrieve the list via `getFieldErrors()` or `getAllErrors()`.

Custom validators should focus on synchronous, lightweight, deterministic rules: non-empty strings, values within range, internal formats, or simple relationships between fields. Do not call databases, HTTP clients, or `block()` inside `validate`.

### 3.2. Field errors and object-level errors

There are two main types of errors:

- **Field error:** attached to a specific property, such as `name`, `price`, or `address.city`.
- **Object/global error:** rules involving multiple fields or the entire object, such as `startDate` must be before `endDate`.

`errors.getFieldErrors()` only gets field errors. `errors.getGlobalErrors()` gets object-level errors. If the API needs to reflect everything, use `errors.getAllErrors()` and represent global errors with an identifier like `"$"` or `"_global"`.

Do not return rejected values by default. Input values may contain passwords, tokens, personal information, or sensitive data. Error responses usually only need the field path and a controlled message.

## 4. Putting Validation into HandlerFunction

A functional handler has the form:

```java
Mono<ServerResponse> create(ServerRequest request)
```

To check the body, the handler reads the publisher and then calls the validator inside `flatMap` or `doOnNext`. Two common approaches:

### 4.1. Throwing ServerWebInputException so WebFlux handles 400

This is the short pattern from the Spring documentation:

```java
public Mono<ServerResponse> create(ServerRequest request) {
    Mono<CreateProductRequest> body =
            request.bodyToMono(CreateProductRequest.class)
                    .doOnNext(this::validate);

    return body.flatMap(productService::create)
            .flatMap(product ->
                    ServerResponse.ok().bodyValue(product));
}

private void validate(CreateProductRequest input) {
    Errors errors =
            new BeanPropertyBindingResult(input, "createProductRequest");

    validator.validate(input, errors);

    if (errors.hasErrors()) {
        throw new ServerWebInputException(errors.toString());
    }
}
```

This is an **illustrative snippet**; `productService.create` must return a reactive publisher. When `validate` throws `ServerWebInputException`, the exception becomes an error of the reactive chain and WebFlux maps the input error to HTTP 400.

The advantage is minimal code and alignment with centralized error handling. The limitation is that `errors.toString()` is not a stable JSON error contract that clients should depend on. If the API needs a custom error structure, you can convert errors into a response directly or build a centralized error-handling mechanism.

### 4.2. Creating a structured 400 response directly in the handler

If you want to control the error body per functional endpoint, you can inspect `Errors` and return `ServerResponse.badRequest()`:

```java
return request.bodyToMono(CreateProductRequest.class)
        .flatMap(input -> {
            Errors errors =
                    new BeanPropertyBindingResult(input, "createProductRequest");
            validator.validate(input, errors);

            if (errors.hasErrors()) {
                return ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(toApiError(errors));
            }

            return productService.create(input)
                    .flatMap(product ->
                            ServerResponse.status(HttpStatus.CREATED)
                                    .contentType(MediaType.APPLICATION_JSON)
                                    .bodyValue(product));
        });
```

This is an **illustrative snippet**. `toApiError` converts `Errors` into a response DTO. The success branch only runs when there are no errors. Both branches return `Mono<ServerResponse>`, so the entire process remains composed within one pipeline.

### 4.3. Do not validate in a separate subscription

Do not do the following:

```java
request.bodyToMono(CreateProductRequest.class)
        .subscribe(this::validate);

return ServerResponse.ok().build();
```

This is an **anti-pattern**. The first subscription reads the body and runs validation independently; the handler immediately returns the response. The validation result no longer determines the response, errors are not in the same pipeline, and request cancellation does not properly manage that branch.

Chain decoding, validation, service, and response with `flatMap`/`map` and return the final publisher.

## 5. Creating a Clear Error Response

An error API can use a structure like:

```json
{
  "code": "VALIDATION_FAILED",
  "violations": [
    {
      "field": "name",
      "message": "name is required"
    },
    {
      "field": "price",
      "message": "price must be greater than zero"
    }
  ]
}
```

Example DTO:

```java
public record FieldViolation(String field, String message) {}

public record ApiValidationError(
        String code,
        List<FieldViolation> violations) {}
```

Conversion function:

```java
private ApiValidationError toApiError(Errors errors) {
    List<FieldViolation> violations = errors.getAllErrors().stream()
            .map(error -> new FieldViolation(
                    error instanceof FieldError fieldError
                            ? fieldError.getField()
                            : "$",
                    error.getDefaultMessage() == null
                            ? "invalid value"
                            : error.getDefaultMessage()))
            .sorted(Comparator.comparing(FieldViolation::field))
            .toList();

    return new ApiValidationError("VALIDATION_FAILED", violations);
}
```

This is an **illustrative snippet** requiring imports for `FieldError`, `Errors`, `Comparator`, and `List`. Sorting by field keeps test output stable and easy to compare. Global errors are placed under the field path `"$"` so the client knows the error is not tied to a single property.

Keep error messages short and free of sensitive rejected values. If the client needs machine-readable logic, you can add a dedicated error code instead of forcing the client to parse prose.

## 6. Validation with Jakarta Bean Validation

Spring Validator is Spring's abstraction; Jakarta Bean Validation provides standard annotations such as `@NotBlank`, `@NotNull`, `@Positive`, `@Email`, and `@Size`.

In a functional handler, you can inject a shared validator based on `LocalValidatorFactoryBean`. With Spring Boot, add:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Spring Boot configures the Bean Validation provider when the starter is present. `LocalValidatorFactoryBean` is the bridge between Jakarta Validation and the Spring validation API; it implements the corresponding abstractions so it can be used in handlers.

DTO:

```java
public class CreateProductRequest {
    @NotBlank(message = "name is required")
    @Size(max = 80, message = "name must be at most 80 characters")
    private String name;

    @NotNull(message = "price is required")
    @Positive(message = "price must be greater than zero")
    private BigDecimal price;

    @NotBlank(message = "sku is required")
    @Pattern(regexp = "[A-Z0-9-]{3,20}",
             message = "sku must contain 3 to 20 uppercase letters, digits or hyphens")
    private String sku;

    @NotNull(message = "address is required")
    @Valid
    private Address address;

    // getters and setters

    public static class Address {
        @NotBlank(message = "city is required")
        private String city;

        @NotBlank(message = "country is required")
        private String country;

        // getters and setters
    }
}
```

When invoking the validator, `@Valid` on the `address` property requests cascading validation into the child object. However, the handler itself still must call `validator.validate(...)`. Annotations do not trigger validation automatically just because a DTO is decoded.

### 6.1. Using SmartValidator in a handler

`org.springframework.validation.SmartValidator` extends Spring Validator to support validation hints, commonly used as validation groups:

```java
@Component
public class ProductHandler {
    private final SmartValidator validator;

    public ProductHandler(SmartValidator validator) {
        this.validator = validator;
    }

    private Errors validate(CreateProductRequest input) {
        Errors errors =
                new BeanPropertyBindingResult(input, "createProductRequest");

        validator.validate(input, errors);
        return errors;
    }
}
```

This is an **illustrative snippet**. In a Spring Boot application with a Bean Validation provider, the default `LocalValidatorFactoryBean` can be injected via the `SmartValidator` interface. If you register multiple validators yourself, use qualifiers or explicitly configure the bean to inject.

### 6.2. Validation groups

One DTO can be used for both create and update. Groups let you select which rules to run depending on the operation:

```java
public interface Create {}
public interface Update {}

public class ProductInput {
    @NotBlank(groups = Create.class)
    private String name;

    @NotNull(groups = Create.class)
    @Positive(groups = {Create.class, Update.class})
    private BigDecimal price;

    // getters and setters
}
```

In the create handler:

```java
Errors errors = new BeanPropertyBindingResult(input, "productInput");
validator.validate(input, errors, Default.class, Create.class);
```

`SmartValidator.validate(target, errors, hints...)` passes groups as validation hints to the Bean Validation provider. If you only select `Create.class`, constraints belonging to the `Default` group do not run automatically unless the group is designed to inherit or is included in the list.

If using the Jakarta `Validator` directly, the corresponding call is:

```java
Set<ConstraintViolation<ProductInput>> violations =
        jakartaValidator.validate(input, Default.class, Create.class);
```

In functional endpoints, `@Validated(Create.class)` on a method argument does not automatically make the handler run the group like an annotated controller. Pass the right groups explicitly via `SmartValidator` or Jakarta `Validator`.

### 6.3. Cascade validation for child objects and collections

`@Valid` on a field/record component takes effect when the validator is invoked:

```java
public class BatchCreateRequest {
    @NotEmpty
    private List<@Valid CreateProductRequest> products;

    // getter and setter
}
```

`@NotEmpty` requires the list to have elements; `@Valid` on elements requests validating each object. For large collections, synchronous validation has CPU cost proportional to the number of elements; limit the request size and item count before processing to avoid uncontrolled resource consumption.

## 7. Distinguishing Empty Body, Malformed JSON, and Validation Failure

These three situations occur at different stages:

| Input | What happens? | How to handle |
| --- | --- | --- |
| No body | `bodyToMono` may complete empty | Use `switchIfEmpty` to emit a "body required" error or a 400 response. |
| Malformed JSON/wrong type | Message reader/codec emits an error during deserialization | Let WebFlux handle the input/decoding error or map it separately at the error layer. |
| Valid JSON that violates constraints | Java object exists; validator records errors | Return 400 with field violations. |

Example of a required body:

```java
Mono<CreateProductRequest> body = request
        .bodyToMono(CreateProductRequest.class)
        .switchIfEmpty(Mono.error(
                new ServerWebInputException("Request body is required")));
```

This is an **illustrative snippet**. `switchIfEmpty` only handles an empty body publisher. It does not catch decode errors because errors are still error signals, not empty completions.

If a uniform error contract is needed, you can handle `ServerWebInputException`/codec exceptions at the WebFlux error-handling layer. Do not turn every decode error into a fake field violation since there is no object to validate yet.

### 7.1. Request content type and codecs

`request.bodyToMono(CreateProductRequest.class)` needs a reader capable of reading the sent Content-Type. For JSON, the client should send `Content-Type: application/json`. If the media type is unsupported or the body cannot be converted, the handler will receive an error signal from reading the body.

For functional endpoints, the router can check predicates such as `contentType(APPLICATION_JSON)` before invoking the handler. This predicate checks the media type; it does not check field constraints and does not replace a validator.

## 8. Runnable Spring Boot 3.3.5 Program

The complete example below uses **Java 17+**, **Maven**, **Spring Boot 3.3.5**, WebFlux functional endpoints, and Jakarta Bean Validation via `SmartValidator`. The handler checks the DTO itself and creates a structured 400 response.

Structure:

```text
functional-validation-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── ValidationApplication.java
    │   ├── CreateProductRequest.java
    │   ├── ProductHandler.java
    │   ├── ProductRoutes.java
    │   └── ProductService.java
    └── test/java/demo/
        └── ProductRoutesTest.java
```

### 8.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>functional-validation-demo</artifactId>
    <version>1.0.0</version>

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
```

### 8.2. ValidationApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationApplication {
    public static void main(String[] args) {
        SpringApplication.run(ValidationApplication.class, args);
    }
}
```

### 8.3. CreateProductRequest.java

```java
package demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

public class CreateProductRequest {
    @NotBlank(message = "name is required")
    @Size(max = 80, message = "name must be at most 80 characters")
    private String name;

    @NotNull(message = "price is required")
    @Positive(message = "price must be greater than zero")
    private BigDecimal price;

    @NotBlank(message = "sku is required")
    @Pattern(regexp = "[A-Z0-9-]{3,20}",
             message = "sku must contain 3 to 20 uppercase letters, digits or hyphens")
    private String sku;

    @NotNull(message = "address is required")
    @Valid
    private Address address;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public BigDecimal getPrice() { return price; }
    public void setPrice(BigDecimal price) { this.price = price; }

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public Address getAddress() { return address; }
    public void setAddress(Address address) { this.address = address; }

    public static class Address {
        @NotBlank(message = "city is required")
        private String city;

        @NotBlank(message = "country is required")
        private String country;

        public String getCity() { return city; }
        public void setCity(String city) { this.city = city; }

        public String getCountry() { return country; }
        public void setCountry(String country) { this.country = country; }
    }
}
```

### 8.4. ProductService.java

```java
package demo;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ProductService {
    private final AtomicLong ids = new AtomicLong();

    public record Product(
            long id,
            String name,
            String sku,
            String price) {}

    public Mono<Product> create(CreateProductRequest request) {
        return Mono.fromSupplier(() ->
                new Product(
                        ids.incrementAndGet(),
                        request.getName(),
                        request.getSku(),
                        request.getPrice().toPlainString()));
    }
}
```

The service only illustrates saving successfully in memory. In a real application, replace it with a reactive repository and handle persistence errors separately.

### 8.5. ProductHandler.java

```java
package demo;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.validation.SmartValidator;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

@Component
public class ProductHandler {
    private final SmartValidator validator;
    private final ProductService service;

    public ProductHandler(SmartValidator validator, ProductService service) {
        this.validator = validator;
        this.service = service;
    }

    public record FieldViolation(String field, String message) {}
    public record ApiError(String code, List<FieldViolation> violations) {}

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateProductRequest.class)
                .switchIfEmpty(Mono.error(
                        new org.springframework.web.server.ServerWebInputException(
                                "Request body is required")))
                .flatMap(input -> {
                    Errors errors = new BeanPropertyBindingResult(
                            input, "createProductRequest");

                    validator.validate(input, errors);

                    if (errors.hasErrors()) {
                        return ServerResponse.badRequest()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(toApiError(errors));
                    }

                    return service.create(input)
                            .flatMap(product ->
                                    ServerResponse.created(
                                                    URI.create("/products/" + product.id()))
                                            .contentType(MediaType.APPLICATION_JSON)
                                            .bodyValue(product));
                });
    }

    private ApiError toApiError(Errors errors) {
        List<FieldViolation> violations = errors.getAllErrors().stream()
                .map(this::toViolation)
                .sorted(Comparator.comparing(FieldViolation::field))
                .toList();

        return new ApiError("VALIDATION_FAILED", violations);
    }

    private FieldViolation toViolation(ObjectError error) {
        String field = error instanceof FieldError fieldError
                ? fieldError.getField()
                : "$";

        String message = error.getDefaultMessage() == null
                ? "invalid value"
                : error.getDefaultMessage();

        return new FieldViolation(field, message);
    }
}
```

### 8.6. ProductRoutes.java

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class ProductRoutes {
    @Bean
    RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
        return RouterFunctions.route()
                .POST("/products", handler::create)
                .build();
    }
}
```

### 8.7. Running the application

In the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Send a valid request:

```bash
curl -i -X POST http://localhost:8080/products \
  -H "Content-Type: application/json" \
  -d '{"name":"Keyboard","price":49.90,"sku":"KEY-100","address":{"city":"Hanoi","country":"VN"}}'
```

The result is HTTP **201 Created**, with header `Location: /products/1` on the first creation and body:

```json
{
  "id": 1,
  "name": "Keyboard",
  "sku": "KEY-100",
  "price": "49.90"
}
```

Send a request violating multiple constraints:

```bash
curl -i -X POST http://localhost:8080/products \
  -H "Content-Type: application/json" \
  -d '{"name":" ","price":-5,"sku":"bad sku","address":{"city":"","country":"VN"}}'
```

The result is HTTP **400 Bad Request**, with a body of the form:

```json
{
  "code": "VALIDATION_FAILED",
  "violations": [
    {"field":"address.city","message":"city is required"},
    {"field":"name","message":"name is required"},
    {"field":"price","message":"price must be greater than zero"},
    {"field":"sku","message":"sku must contain 3 to 20 uppercase letters, digits or hyphens"}
  ]
}
```

The list is sorted by field so the output is stable. The actual violations are produced by the validator; if you add constraints, the response will include the corresponding errors.

### 8.8. ProductRoutesTest.java

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ProductRoutesTest {
    @Autowired
    WebTestClient client;

    @Test
    void validRequestCreatesProduct() {
        client.post()
                .uri("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "Keyboard",
                          "price": 49.90,
                          "sku": "KEY-100",
                          "address": {
                            "city": "Hanoi",
                            "country": "VN"
                          }
                        }
                        """)
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().valueEquals("Location", "/products/1")
                .expectBody()
                .jsonPath("$.name").isEqualTo("Keyboard")
                .jsonPath("$.sku").isEqualTo("KEY-100");
    }

    @Test
    void invalidRequestReturnsFieldViolations() {
        client.post()
                .uri("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": " ",
                          "price": -5,
                          "sku": "bad sku",
                          "address": {
                            "city": "",
                            "country": "VN"
                          }
                        }
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("VALIDATION_FAILED")
                .jsonPath("$.violations").isArray()
                .jsonPath("$.violations[0].field")
                    .isEqualTo("address.city");
    }

    @Test
    void missingBodyReturnsBadRequest() {
        client.post()
                .uri("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isBadRequest();
    }
}
```

Run:

```bash
mvn test
```

The tests confirm that a valid request creates the product, a request with constraint violations returns 400 with an error body, and an empty body is rejected. This integration test verifies the actual HTTP contract of the RouterFunction/HandlerFunction and the Spring-injected validator.

## 9. Using a Self-Written Spring Validator Instead of Annotation Constraints

Not every project needs Jakarta Bean Validation. When rules are simple, or compatibility with an existing Spring validation system is needed, you can create a custom `Validator`:

```java
@Component
public class ProductInputValidator implements Validator {
    @Override
    public boolean supports(Class<?> type) {
        return ProductInput.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        ProductInput input = (ProductInput) target;

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "name", "name.required", "name is required");

        if (input.getQuantity() == null) {
            errors.rejectValue(
                    "quantity", "quantity.required", "quantity is required");
        } else if (input.getQuantity() <= 0) {
            errors.rejectValue(
                    "quantity", "quantity.positive",
                    "quantity must be greater than zero");
        }
    }
}
```

This is a **standalone illustrative snippet**, assuming `ProductInput` has JavaBean getters/setters. The handler uses it just like the validator in the main example. If there are multiple validators for the same DTO, you can call them sequentially or coordinate via `SmartValidator`/a dedicated configuration; avoid creating a new validator on every request if it has dependencies or shared state.

### 9.1. When to use Jakarta Validator directly?

If you need to get a set of `ConstraintViolation<T>` instead of Spring `Errors`:

```java
Set<ConstraintViolation<CreateProductRequest>> violations =
        jakartaValidator.validate(input);

if (!violations.isEmpty()) {
    // Convert violation.getPropertyPath() and getMessage()
    // into an API error response.
}
```

`jakarta.validation.Validator` is suitable when logic needs to use the standard Jakarta API directly, or when you want to share the same validator with another Java component. `LocalValidatorFactoryBean` allows integration with Spring. If the handler needs `Errors` and validation hints, `SmartValidator` is more convenient.

## 10. Asynchronous Rules Must Live in a Reactive Service

Bean Validation and Spring `Validator` are both synchronous call APIs. A validator does not return `Mono<Boolean>`; it runs on the thread calling `validate`.

Example of what not to do:

```java
@Override
public void validate(Object target, Errors errors) {
    ProductInput input = (ProductInput) target;
    boolean exists = repository.existsBySku(input.getSku()).block();
    if (exists) {
        errors.rejectValue("sku", "sku.exists", "sku already exists");
    }
}
```

This is an **anti-pattern**. The query can block the event loop, reducing throughput and causing errors when blocking on threads that forbid blocking. It also mixes synchronous validation with asynchronous I/O.

Split it into two stages:

1. The validator checks form and structure: is the SKU formatted properly, does the name have a value, is quantity positive.
2. The service checks external state: does the SKU already exist, does the user have permission to create the product, is quota sufficient.

Example:

```java
return request.bodyToMono(CreateProductRequest.class)
        .flatMap(input -> {
            Errors errors = validate(input);
            if (errors.hasErrors()) {
                return badRequestResponse(errors);
            }

            return productRepository.existsBySku(input.getSku())
                    .flatMap(exists -> {
                        if (exists) {
                            return conflictResponse("SKU_ALREADY_EXISTS");
                        }
                        return productService.create(input)
                                .flatMap(this::createdResponse);
                    });
        });
```

This is an **illustrative snippet**; the repository and helpers must return reactive publishers. Use `flatMap` to wait for the asynchronous result and decide the response. If two concurrent requests both check that the SKU does not exist yet, both can still pass the check before writing; the database needs a unique constraint and the service must handle the duplicate-key race condition.

## 11. Points to Watch in Functional Handlers

### 11.1. The body should only be read once

`request.bodyToMono(CreateProductRequest.class)` consumes the request body along the pipeline. Do not create a separate subscription to log the body and then decode again. If you need to log data, prefer non-sensitive metadata or design a bounded body-reading/replaying step with clear buffer management.

### 11.2. Validation failure must prevent side effects

The right order is decode → validate → service. Do not write to a database, send a message, or call an external API before knowing the object is valid. If validation fails, the service must not run.

### 11.3. Validate the entire object when needed

`validator.validate(input, errors)` checks the `Default` group by default. For nested DTOs, place `@Valid` on properties that need cascading. For class-level constraints, validators can add global errors. For collections, check size and cascade each element.

### 11.4. Validation does not replace authorization

A request may be valid in data type yet the sender lacks permission to perform the action. Permission checks must rely on the authenticated principal and server-side policies. Do not treat `ownerId`, `role`, or `tenantId` fields in JSON as proof that the user has ownership rights.

### 11.5. Limit request and collection sizes

Validation takes place after the codec has deserialized the object. With a very large body, the application has already consumed resources before the validator runs. Configure memory/body size limits at the server/codec level, limit element counts, and use streaming when data is truly large.

### 11.6. Error messages and localization

Spring Validator and Bean Validation can use message codes/MessageSource. In public APIs, choose consistent messages that can be localized per locale and do not expose internal structure. If clients need machine-readable logic, return stable error codes along with field paths; do not force clients to compare translated prose.

## 12. Common Mistakes and How to Handle Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking `@Valid` runs automatically in WebFlux.fn | DTO has annotations but is not validated | Inject the validator and invoke it explicitly in the handler. |
| Only calling `bodyToMono` and then saving data | Decode succeeds but constraints are not checked | Add validation before service/persistence. |
| Calling `validator.validate` before the body is decoded | No object yet to check | Place the validator inside `flatMap`/`doOnNext` after body extraction. |
| Using `request.bind` to read a JSON body | Confuses path/query/header binding with body codecs | Use `bodyToMono`/`bodyToFlux` for the body. |
| Using `Errors` but only reading `getFieldErrors()` | Misses object-level errors | Read `getAllErrors()` when completeness is needed. |
| Returning 200 even though errors exist | Client assumes request was accepted | Return `ServerResponse.badRequest()` or throw `ServerWebInputException`. |
| Including rejected values/stack traces in responses | Can expose sensitive data | Only return field paths and public messages. |
| Thinking type-mismatched JSON is a validation violation | No DTO exists yet to validate | Handle decode errors separately from Bean Validation. |
| Ignoring an empty body | Handler may complete empty and fail to create the expected response | Use `switchIfEmpty` and require the body. |
| Calling `subscribe()` inside a handler | Detaches side effects from the HTTP lifecycle | Compose with `flatMap` and return the publisher. |
| Calling `block()` in a validator | Blocks the event loop | Validate synchronously only; move I/O to a reactive service. |
| Querying a database inside a ConstraintValidator | Synchronous validator blocks on I/O | Check external data in the service using a publisher. |
| Using `@Validated` and thinking groups are chosen automatically in a handler | No automatic validator invocation like annotated arguments | Call `SmartValidator.validate(..., group)` or Jakarta `Validator.validate(..., group)`. |
| Forgetting to cascade on child objects | Nested constraints do not run | Place `@Valid` on the property/collection element. |
| Not limiting large bodies/lists | Validation can consume significant CPU/memory | Set request and element-count limits before processing. |
| Only checking existence then writing data | Race condition between two concurrent requests | Use a unique constraint and handle conflicts at the persistence layer. |
| Using validation instead of authorization | Users can submit valid data without permission | Authenticate and check permissions with Spring Security/policies. |

## 13. Self-Check Questions

**Question 1.** Why does a WebFlux functional handler need to invoke a validator explicitly?  
**Answer:** The handler receives `ServerRequest` and reads the body itself; there is no annotated method argument resolver that automatically triggers validation for the DTO. After decoding, the handler must call `Validator.validate` or Jakarta `Validator.validate`.

**Question 2.** Has `request.bodyToMono(CreateProductRequest.class)` checked `@NotBlank` yet?  
**Answer:** Not yet. It reads and deserializes the body. You must call the validator after obtaining the object.

**Question 3.** What is the role of `BeanPropertyBindingResult`?  
**Answer:** It creates an `Errors` container bound to the object, storing field errors and global errors so the handler can decide the response.

**Question 4.** What is `ServerWebInputException` commonly used for in functional endpoints?  
**Answer:** Throwing an input error when validation fails; WebFlux handles this exception as HTTP 400 under the default mechanism.

**Question 5.** Why should you not call a database inside `Validator.validate`?  
**Answer:** Spring Validator/Jakarta Bean Validation are synchronous APIs. Blocking queries can stall the event loop. Checks that depend on I/O should live in a reactive service.

**Question 6.** What does `@Valid` on the nested address do?  
**Answer:** When the validator is actually invoked, it cascades into the address object and checks the constraints inside.

**Question 7.** How do you select the Create group in a handler?  
**Answer:** Use `SmartValidator.validate(input, errors, Default.class, Create.class)` or Jakarta `Validator.validate(input, Default.class, Create.class)`. `@Validated` does not automatically trigger validation in WebFlux.fn.

**Question 8.** What kind of error is JSON having `"price": "many"` when the DTO expects `BigDecimal`?  
**Answer:** A deserialization/codec error that occurs before validation. There is no valid object yet to check the positive-price constraint.

**Question 9.** If validation fails, is the service called?  
**Answer:** No. The handler must check errors before composing service create/save.

**Question 10.** What can happen if two requests both pass a "SKU does not exist" check and then write concurrently?  
**Answer:** A race condition. You need a unique constraint in the database and handling for duplicate-key errors; application-layer validation does not guarantee uniqueness under concurrency.

## Key Takeaways

- In WebFlux.fn, `HandlerFunction` receives `ServerRequest` and returns `Mono<ServerResponse>`. The handler reads the body with `bodyToMono`/`bodyToFlux` and then **explicitly calls the validator**.
- `Spring Validator` uses `Errors` and `BeanPropertyBindingResult`; `SmartValidator` adds validation hints/groups. Jakarta Bean Validation can be integrated via `LocalValidatorFactoryBean`.
- `@Valid` on a nested DTO enables cascading when the validator is invoked; `@Validated` does not automatically trigger validation in functional handlers.
- Decode errors, empty bodies, and constraint violations are three distinct situations. Choose explicit handling and 4xx responses.
- Synchronous validation only checks structure and lightweight rules. Checks requiring database/network access must be composed with `Mono`/`Flux` in the service.
- Always validate before side effects, return a safe error contract, limit bodies and collections, and do not `block()` or `subscribe()` manually.

### References

1. [Spring Framework – WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): `HandlerFunction`, `ServerRequest.bodyToMono`, and examples of validation using Spring `Validator`.
2. [Spring Framework – Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Spring Validator, Jakarta Bean Validation, `LocalValidatorFactoryBean`, and validation groups.
3. [Spring Boot – Validation](https://docs.spring.io/spring-boot/reference/io/validation.html): configuring the provider via `spring-boot-starter-validation`.
4. [Spring Framework – WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html): `ServerWebInputException` and HTTP error handling.
5. [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): constraint annotations, cascade validation, groups, and `ConstraintValidator`.
6. [Spring Framework – WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing reactive HTTP endpoints.
