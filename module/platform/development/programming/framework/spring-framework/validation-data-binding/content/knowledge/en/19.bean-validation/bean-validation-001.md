# Jakarta Validation and the Declarative Constraint Model in Spring Framework

> **Module:** Spring Framework – validation-data-binding  
> **Parent Topic:** Bean Validation  
> **Focus:** How to declare, organize, and execute *constraints* with `jakarta.validation`; the relationship between Jakarta Validation, a provider such as Hibernate Validator, and Spring's data binding process.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain Jakarta Validation (formerly Bean Validation) and the meaning of **declarative annotation-based** data validation.
2. Distinguish **constraint**, **constraint validator**, **validation provider**, **Validator**, and **ConstraintViolation**.
3. Place built-in constraints on fields, getters, parameters, types, collection elements, and nested objects.
4. Combine `@NotNull`, `@NotBlank`, `@Size`, `@Pattern`, `@Email`, `@Positive`, `@Past`, etc. with the right semantics, especially regarding `null` values.
5. Use `@Valid`, validation groups, container element constraints, and custom `@Constraint` annotations.
6. Proactively invoke `jakarta.validation.Validator` for testing, then integrate `@Valid`/`@Validated` into Spring MVC.
7. Recognize the boundaries between **binding**, **Bean Validation**, business rules, and database constraints.

## 2. What is Jakarta Validation?

**Jakarta Validation** is the standard specification in the Jakarta EE ecosystem for declaring and validating Java data. Instead of writing repetitive `if` statements in controllers, you attach annotations directly where data is defined:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class RegistrationForm {
    @NotBlank
    @Size(max = 80)
    private String fullName;

    @NotBlank
    @Email
    private String email;
}
```

The snippet above is an **illustrative model**, not a standalone runnable program. The annotations state that the name must not be blank and can be at most 80 characters long; the email must not be blank and must satisfy the validator's email rule. The declaration **does not run validation automatically**: there must be a call to `Validator.validate(...)` or a framework triggering validation at an integration point.

Starting with Spring Framework 6 / Spring Boot 3, use the **`jakarta.validation.*`** package. Legacy code uses `javax.validation.*` from the previous library generation; do not mix the two namespaces in the same application when upgrading.

Components:

| Component | Meaning | Example |
| --- | --- | --- |
| **Constraint annotation** | Declares a rule on an object | `@NotBlank`, `@Min(1)`, `@ValidOrderCode` |
| **ConstraintValidator** | Code that executes the rule for supported types | `ConstraintValidator<OrderCode, String>` |
| **Validation provider** | Implements the specification, discovers metadata, and runs validation | Hibernate Validator |
| **ValidatorFactory** | Creates and manages `Validator` instances | `Validation.buildDefaultValidatorFactory()` |
| **Validator** | Validates a bean and returns a set of errors | `validator.validate(order)` |
| **ConstraintViolation** | Result of each failed rule | Property path, message, invalid value, metadata |

Jakarta Validation is an **API and behavioral contract**; Hibernate Validator is a popular **implementation**. Spring provides integration points such as `LocalValidatorFactoryBean`, `@Valid` on controller parameters, and `@Validated` for using groups. Spring and Jakarta Validation have separate responsibilities, not two names for the same component.

## 3. Declarative Model of a Constraint

A constraint has three conceptual layers:

```text
[Object to validate]
        |
        |  @NotBlank(message = "Must not be blank")
        v
[Constraint metadata]
        |
        v
[Validation provider] -- finds compatible ConstraintValidators
        |
        v
[isValid(value, context)]
        |
        +-- true  -> creates no error for that rule
        |
        +-- false -> ConstraintViolation
                     propertyPath, message, invalidValue, descriptor...
```

A standard or custom constraint can be placed wherever the annotation allows:

- **Field:** `@NotNull private String name;` — the provider reads the field directly, even if the field is private.
- **JavaBean getter:** `@NotNull public String getName()` — the provider uses the property getter.
- **Class/type:** custom constraint checking relationships across multiple fields, e.g., `startDate <= endDate`.
- **Method/constructor parameter and return value:** validates method contracts via executable validation or framework integration.
- **Container element:** `List<@NotBlank String>` or `Map<@NotBlank String, @Valid Address>`.
- **Record component:** with modern Java and a compatible provider, constraints can be placed on record components.

**Do not accidentally place the same constraint on both the field and getter** of the same property if you do not want the rule potentially evaluated twice. Choose a consistent declaration strategy.

### 3.1. An annotation does not automatically catch errors on assignment

For example:

```java
User user = new User();
user.setName("");
```

If `User.name` has `@NotBlank`, a normal setter call still assigns the empty string. Constructing a bean or calling a setter does not automatically throw `ConstraintViolationException`. Errors appear when calling `Validator` or when Spring, JPA, a method interceptor, etc. actually triggers validation. Constraints remain merely metadata if not executed.

### 3.2. Each validation run can produce multiple errors

`Validator.validate(bean)` returns a `Set<ConstraintViolation<T>>`. This set **does not guarantee error ordering**. If deterministic test results are needed, sort by `getPropertyPath()` and then by message. Do not build logic that depends on "which constraint runs first" when constraints are in the same group, unless a group sequence is explicitly declared.

## 4. Built-in Constraints and How to Choose Them

Representative annotations in `jakarta.validation.constraints`:

| Annotation | Constraint | Example | Notes |
| --- | --- | --- | --- |
| `@NotNull` | Value is not `null` | `@NotNull Long id` | Strings `""` and `" "` are still non-null |
| `@Null` | Value must be `null` | `@Null Long generatedId` | Useful for server-generated fields |
| `@NotEmpty` | Not null and not empty | `@NotEmpty List<String> tags` | For strings, `" "` is still considered non-empty |
| `@NotBlank` | String has at least one non-whitespace character | `@NotBlank String name` | For `CharSequence` |
| `@Size(min=..., max=...)` | Size of string, collection, map, or array | `@Size(min=2,max=50)` | `null` is considered valid; pair with `@NotNull` if needed |
| `@Min`, `@Max` | Integer value bounds | `@Min(1) int count` | `@Min`/`@Max` accept `long` thresholds |
| `@DecimalMin`, `@DecimalMax` | Decimal bounds, with optional `inclusive=false` | `@DecimalMin("0.01")` | Uses strings for bound values |
| `@Positive`, `@PositiveOrZero` | Positive / non-negative number | `@Positive Integer quantity` | `null` is typically valid |
| `@Negative`, `@NegativeOrZero` | Negative / non-positive number | `@Negative BigDecimal balance` | Choose according to domain semantics |
| `@Digits(integer=..., fraction=...)` | Number of integer/fractional digits | `@Digits(integer=8,fraction=2)` | Does not replace business min/max bounds |
| `@Pattern(regexp=...)` | String matches regex | `@Pattern(regexp="[A-Z]{2}[0-9]{3}")` | `null` is valid; applies to `CharSequence` |
| `@Email` | Email syntax according to the validator | `@Email String email` | Does not prove the email exists; pair with `@NotBlank` if required |
| `@Past`, `@PastOrPresent` | Time in the past / not beyond present | `@Past LocalDate birthday` | Uses the clock from `ClockProvider` |
| `@Future`, `@FutureOrPresent` | Time in the future / not before present | `@Future LocalDate expiry` | Avoids depending on test execution time |
| `@AssertTrue`, `@AssertFalse` | Expected boolean value | `@AssertTrue Boolean accepted` | `null` is valid; pair with `@NotNull` if required |

Two very common misconceptions:

```java
@NotNull
private String description; // "" is still valid for @NotNull alone

@NotBlank
private String displayName; // null, "", "   " are all invalid
```

Constraints like `@Size`, `@Pattern`, `@Positive`, `@Email`, and `@Past` generally allow `null`; they check **a present value**, while whether a value may be missing is decided by `@NotNull`/`@NotBlank`/`@NotEmpty`. Do not infer that `@Email` automatically makes an email required.

`@Size(min=1)` and `@NotBlank` also differ: a string containing only a single space has enough characters for `@Size(min=1)`, but fails `@NotBlank`.

## 5. Declaring on Fields, Nested Objects, and Collections

### 5.1. Validating properties of a bean

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public class ProductRequest {
    @NotBlank(message = "Product name is required")
    @Size(max = 120)
    private String name;

    @NotNull
    @Positive
    private Integer quantity;

    // Constructor, getters, setters depending on DTO architecture
}
```

This is an **illustrative DTO fragment**, not a class with `main`. For `quantity`, `@NotNull` rejects the missing case and `@Positive` rejects 0 or negative numbers; the two constraints complement rather than replace each other.

### 5.2. `@Valid` for associated objects

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class CheckoutRequest {
    @NotNull
    @Valid
    private Address shippingAddress;
}

public class Address {
    @NotBlank
    private String city;
}
```

**Meaning:** `@NotNull` requires an address to be present; `@Valid` instructs the validator to traverse into the `Address` object and check `city`. If `@Valid` is omitted, only constraints on the parent's `shippingAddress` field are evaluated, while constraints on the child class are not automatically scanned. If the address is `null`, cascading does not run; `@NotNull` catches that error.

In complete models with multiple classes, the same idea applies to `Order -> Customer -> Address`, though you should avoid complex object cycles and avoid validating unnecessary object graphs.

### 5.3. Container element constraints

In modern Jakarta Validation versions, annotations can be applied directly to element types:

```java
import java.util.List;
import java.util.Map;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public class BatchRequest {
    @NotEmpty
    private List<@NotBlank String> codes;

    private Map<@NotBlank String, @Valid Address> addressByLabel;

    private List<@NotNull Integer> positions;
}
```

- Outer `@NotEmpty` checks that **the list has elements**.
- Inner `@NotBlank` checks **each string**.
- `@Valid` on the `Map` value requests validating each `Address`.
- `@NotNull` on `Integer` checks that each position is non-null.

`@Valid` and container element constraints are two different things: one triggers **cascading into child beans**, while the other checks **each element**. For custom containers, the provider needs an appropriate `ValueExtractor`; not every arbitrary generic type is supported automatically.

## 6. Validation Groups: One DTO, Multiple Contexts

Some properties are required on creation but optional on update, or vice versa. Groups partition the set of constraints to evaluate:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

interface OnCreate {}
interface OnUpdate {}

class DocumentCommand {
    @NotNull(groups = OnUpdate.class)
    private Long id;

    @NotBlank(groups = {OnCreate.class, OnUpdate.class})
    private String title;
}
```

The `OnCreate` and `OnUpdate` declarations are **marker interfaces** and need no methods. Example:

```java
validator.validate(command, OnCreate.class);
validator.validate(command, OnUpdate.class);
```

- When validating `OnCreate`: checks `title` for the Create group; the `id` constraint in Update does not belong to this pass.
- When validating `OnUpdate`: checks both `id` and `title`.
- Constraints that do not specify `groups` belong to `jakarta.validation.groups.Default` by default.
- Calling `validate(bean, OnCreate.class)` **does not automatically include the `Default` group** unless the group has an appropriate inheritance/sequence structure declared.

`@GroupSequence` can be used to specify group order and stop evaluating subsequent groups if an earlier group has errors. Do not assume that constraints within the same group run in the order they are written on fields.

In Spring, `@Validated(OnCreate.class)` (from `org.springframework.validation.annotation.Validated`) allows selecting groups at the integration point; `@Valid` (from `jakarta.validation.Valid`) primarily requests validation/cascading using the current context's default group. **Do not confuse the two annotations because they live in different packages.**

## 7. Defining a Custom Constraint

Built-in annotations cannot express every rule. For example, an order code must follow the pattern `ORD-` followed by exactly three digits.

A **custom constraint annotation** requires:

1. `@Constraint(validatedBy = ...)`: links to the implementation.
2. `@Retention(RUNTIME)`: metadata must be present at runtime.
3. `@Target(...)`: restricts where it can be attached.
4. Three required attributes: `String message()`, `Class<?>[] groups()`, `Class<? extends Payload>[] payload()`.
5. A `ConstraintValidator<AnnotationType, ValueType>` implementing the logic in `isValid(...)`.

Additional attributes such as `min`, `max`, or `prefix` can be added to configure each usage of the annotation. `payload` is where application metadata is attached; Jakarta Validation does not inherently interpret it as an HTTP status, error level, or UI severity.

### 7.1. Choosing a convention for null

For custom constraints checking **format**, `null` is usually treated as valid:

```java
@Override
public boolean isValid(String value, ConstraintValidatorContext context) {
    return value == null || value.matches("ORD-[0-9]{3}");
}
```

Then place `@NotNull` or `@NotBlank` if the field is required. This separates "missing value" errors from "invalid format" errors. Not every constraint must treat null as valid; a custom constraint can be designed differently, but it must be clearly defined and tested.

**`ConstraintValidator` instances may be reused and called concurrently by the provider**; do not store the value being validated in shared mutable fields. If needed, `initialize(annotation)` should only read annotation configuration to prepare logic; `isValid` must not mutate the input object.

### 7.2. Class-level constraints

If the requirement is `start <= end`, a `@ValidDateRange` with `@Target(TYPE)` and `ConstraintValidator<ValidDateRange, Booking>` is more appropriate than applying `@Future` to each field individually. The validator class reads both `start` and `end` and returns the result of the relationship. `ConstraintValidatorContext` can be used to attach the error to a specific property path rather than only on the root bean.

Do not query the database or call network APIs from `isValid` on every validation request without a clear business reason; cases requiring external data should be designed and controlled at the service layer.

### 7.3. Constraint composition

A new annotation can also **combine multiple built-in constraints**, such as `@NotBlank` and `@Size`, by placing those annotations on the custom annotation definition. `@ReportAsSingleViolation` is used when you want to report one composite error instead of each individual sub-error. This is a declarative mechanism, distinct from writing a `ConstraintValidator` for arbitrary checks.

## 8. Complete Java 17+ Example: Calling Jakarta Validator Directly

The following example demonstrates built-in constraints, a custom constraint, and `@Valid` cascading. Spring Web is not required, but **Jakarta Validation API and an implementation** are required.

Structure:

```text
validation-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── validation/
                    └── ValidationDemo.java
```

`pom.xml` file (Maven with Java 17; Hibernate Validator 8 is a provider for the Jakarta Validation 3.0 API):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>validation-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.1.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Hibernate Validator brings in the `jakarta.validation` API via dependencies; the EL dependency provides the expression-language implementation for default message interpolation. Real projects should use compatible versions managed via dependency management; the versions above are solely for reproducible practice.

`src/main/java/example/validation/ValidationDemo.java` file:

```java
package example.validation;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Comparator;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.Payload;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public class ValidationDemo {

    @Documented
    @Constraint(validatedBy = OrderCodeValidator.class)
    @Target({ElementType.FIELD, ElementType.PARAMETER})
    @Retention(RetentionPolicy.RUNTIME)
    public @interface OrderCode {
        String message() default "code format invalid";
        Class<?>[] groups() default {};
        Class<? extends Payload>[] payload() default {};
    }

    public static class OrderCodeValidator
            implements ConstraintValidator<OrderCode, String> {

        @Override
        public boolean isValid(
                String value, ConstraintValidatorContext context) {
            return value == null || value.matches("ORD-[0-9]{3}");
        }
    }

    public static class Address {
        @NotBlank(message = "city is required")
        private final String city;

        public Address(String city) {
            this.city = city;
        }
    }

    public static class OrderRequest {
        @NotBlank(message = "code is required")
        @OrderCode
        private final String code;

        @NotNull(message = "quantity is required")
        @Positive(message = "quantity must be positive")
        private final Integer quantity;

        @NotNull(message = "address is required")
        @Valid
        private final Address address;

        public OrderRequest(String code, Integer quantity, Address address) {
            this.code = code;
            this.quantity = quantity;
            this.address = address;
        }
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            OrderRequest bad =
                    new OrderRequest("BAD", 0, new Address(" "));

            validator.validate(bad).stream()
                    .map(v -> v.getPropertyPath() + ": " + v.getMessage())
                    .sorted(Comparator.naturalOrder())
                    .forEach(System.out::println);

            OrderRequest good =
                    new OrderRequest("ORD-123", 2, new Address("Ha Noi"));
            System.out.println("valid-count="
                    + validator.validate(good).size());
        }
    }
}
```

Run inside the `validation-demo` directory:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=example.validation.ValidationDemo
```

Lines printed by the program to **stdout** (excluding Maven or library logs/notices):

```text
address.city: city is required
code: code format invalid
quantity: quantity must be positive
valid-count=0
```

Explanation:

- `code="BAD"` is not blank, so `@NotBlank` passes; `@OrderCode` fails.
- `quantity=0` is not null, so `@NotNull` passes; `@Positive` fails.
- `address` is not null, but `@Valid` descends into `address.city=" "`, causing `@NotBlank` to fail.
- On `good`, every constraint passes, and `validate(good).size()` equals 0.
- `sorted(...)` makes the printed order deterministic; without sorting, the order of `Set<ConstraintViolation>` is not guaranteed.
- `ValidatorFactory` is closed via `try-with-resources` after use.

The example can test each `null` case separately: `@OrderCode` in this example treats `null` as valid, while `@NotBlank` or `@NotNull` rejects missing values.

## 9. Integration with Spring MVC / Spring Boot

In Spring Boot 3+, commonly needed dependencies:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

These dependencies belong to a Spring Boot project whose parent/BOM manages versions. **Adding starter-web does not guarantee a validation provider is present in every configuration**; starter-validation provides the common integration with Hibernate Validator.

The following example is a single-file Spring Boot Java 17+ application using `@Valid @RequestBody` to validate JSON requests before running business logic.

`src/main/java/example/webvalidation/ValidationWebApplication.java` file:

```java
package example.webvalidation;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ValidationWebApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationWebApplication.class, args);
    }

    public record AddressRequest(
            @NotBlank String city) {}

    public record CreateCustomerRequest(
            @NotBlank String name,
            @NotBlank @Email String email,
            @NotNull @Valid AddressRequest address) {}

    @RestController
    @RequestMapping("/customers")
    public static class CustomerController {

        @PostMapping
        public Map<String, String> create(
                @Valid @RequestBody CreateCustomerRequest request) {
            return Map.of(
                    "name", request.name(),
                    "city", request.address().city());
        }
    }
}
```

Assuming the application runs on port `8080`. Valid request:

```bash
curl -i -X POST http://localhost:8080/customers \
  -H "Content-Type: application/json" \
  -d '{"name":"Lan","email":"lan@example.com","address":{"city":"Ha Noi"}}'
```

The controller returns JSON containing `name` and `city`; the order of JSON keys is not guaranteed.

Invalid request:

```bash
curl -i -X POST http://localhost:8080/customers \
  -H "Content-Type: application/json" \
  -d '{"name":"","email":"invalid","address":{"city":""}}'
```

With the default integration, failing constraints cause Spring MVC to return HTTP **400** before entering the body of `create(...)`; the exact JSON error response shape depends on the application's error handling configuration. JSON data is **deserialized by Jackson** into `CreateCustomerRequest`; then Jakarta Validation checks the annotations. Invalid JSON parsing can be rejected at the conversion step before validation occurs.

### 9.1. How does data binding differ from Bean Validation?

```text
HTTP request
   |
   v
[Read and convert] -- Jackson / HttpMessageConverter / WebDataBinder
   |               -- invalid JSON syntax, type mismatch, bad date format... -> binding error
   v
[DTO constructed]
   |
   v
[Jakarta Validation] -- @NotNull / @Size / @Valid / custom constraint
   |                 -- ConstraintViolation / errors
   v
[Controller handles business logic] -- existence check, authorization,
                                       state consistency, transactions...
```

Validation does not replace the conversion step, and succeeding at both steps does not prove overall business validity.

### 9.2. `@Valid` and `@Validated` in Spring

- `@Valid` is the standard Jakarta annotation, commonly used on `@RequestBody`, `@ModelAttribute`, and nested properties to trigger validation/cascading.
- `@Validated` is a Spring annotation, used when **validation groups** are needed and in certain Spring-driven method validation mechanisms.
- With `@ModelAttribute`, `BindingResult` can be placed immediately after the parameter to validate in order to handle errors directly inside the controller.
- With standard `@RequestBody`, `@Valid` can raise `MethodArgumentNotValidException`; Spring MVC translates this to HTTP 400 by default.
- Starting in Spring Framework 6.1, if a method has constraints directly on parameters or its return value, the built-in method validation mechanism can raise `HandlerMethodValidationException`. If an application places `@Validated` at the controller class level, the AOP method validation mechanism may be used instead; distinguish this from the MVC built-in mechanism when configuring.

**Group selection example** (illustrative snippet inside a controller with defined DTOs/groups):

```java
@PostMapping("/drafts")
public void create(
        @Validated(OnCreate.class) @RequestBody DocumentCommand request) {
    // Handle when OnCreate group constraints are valid.
}
```

Writing `@Validated(OnCreate.class)` does not automatically run constraints belonging to the `Default` group, unless corresponding group rules apply.

## 10. Constraints on Methods and Constructors

Jakarta Validation can declare method input/output contracts:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public interface PricingService {
    @Positive
    long calculatePrice(@NotBlank String productCode);
}
```

The snippet above is an **illustrative interface**. Annotations do not execute merely because of a plain Java call to `calculatePrice`. A mechanism invoking `ExecutableValidator` or Spring method validation/AOP integration (depending on version and location) is needed. Constraints on return values and parameters check two different points in time. Do not mechanically add class-level `@Validated` when the project already uses Spring MVC 6.1+ built-in method validation.

For cross-parameter constraints (e.g., `start` must not be after `end` across two parameters), a validator supporting the `PARAMETERS` target is needed; this differs from a class-level constraint checking two fields on a DTO. This is an extension when the method model genuinely requires it.

## 11. Error Messages, Metadata, and i18n

Each constraint has a `message`:

```java
@NotBlank(message = "{user.name.required}")
private String name;
```

The provider can interpolate message keys from the `ValidationMessages.properties` resource bundle. A `message` can contain placeholders like `{min}`, `{max}` for constraints with matching attributes. In Spring, configuring `MessageSource` and `LocalValidatorFactoryBean` can unify localization; details depend on application configuration.

`ConstraintViolation` results typically provide:

| API | Meaning |
| --- | --- |
| `getPropertyPath()` | Path to the violating field or node, potentially including container elements |
| `getMessage()` | Interpolated message |
| `getMessageTemplate()` | Original message template, such as a message key |
| `getInvalidValue()` | Offending value (be careful when logging user data) |
| `getRootBean()` | Root object being validated |
| `getConstraintDescriptor()` | Annotation metadata, attributes, groups, validators, etc. |

Applications can map errors into a stable structure like `field`, `code`, `message`, though that is an API design decision. Do not rely on the provider's default English messages to construct business error codes.

## 12. Common Design Mistakes and Misconceptions

1. **Calling `new Dto(...)` and expecting annotations to run automatically.** You must invoke `Validator` or let an integrated framework execute it.
2. **Using only `@Size` for a required field.** `null` can pass through; add `@NotNull` or `@NotBlank` depending on data type.
3. **Assuming `@Email` verifies an address can receive mail.** It only checks syntax according to the validator.
4. **Using `@NotBlank` on numbers or collections.** `@NotBlank` is for strings; for collections choose `@NotEmpty`, `@Size`.
5. **Placing constraints on a child bean while forgetting `@Valid` on the parent relation.** Validation does not descend into the child object.
6. **Placing `@NotEmpty` on a list and thinking each item is also valid.** Constraints are needed on the generic type argument.
7. **Using a Create group while expecting `Default` to be checked too.** Groups/sequences must be designed explicitly.
8. **Mixing `javax.validation` with `jakarta.validation` when upgrading to Spring 6/Boot 3.** Use the version-compatible namespace/API.
9. **Writing custom validators that always return false on null without considering design.** Separating "missing" and "invalid format" prevents unclear error reporting.
10. **Using field constraints for conditions involving two fields.** Consider a class-level constraint or service-layer business validation.
11. **Relying on the order of returned `ConstraintViolation`s.** The result is a `Set`; sort if a fixed order is needed.
12. **Treating Jakarta Validation as a replacement for DB constraints.** Uniqueness rules, foreign keys, race conditions, and transactional consistency still need enforcement in the database/service.
13. **Validating overly broad data unnecessarily.** Choose boundaries, DTOs, cascades, and groups intentionally; do not accidentally validate the entire entity graph.
14. **Conflating binding errors with Bean Validation errors as one cause.** Data type errors can fail before constraints are ever evaluated.

## 13. Self-Assessment Exercises

**Exercise 1.** A form has a required `String username` that cannot be whitespace-only and has a maximum of 32 characters. What should be declared?

```java
@NotBlank
@Size(max = 32)
private String username;
```

**Exercise 2.** `List<String> tags` must have at least one element, and each element must not be empty/whitespace-only.

```java
@NotEmpty
private List<@NotBlank String> tags;
```

**Exercise 3.** Why is `@Positive Integer quantity` alone insufficient if `quantity` is required? Because `@Positive` does not treat `null` as invalid; `@NotNull` must be added.

**Exercise 4.** A DTO contains `Address address`, and `Address` has `@NotBlank city`. The `address` field only has `@NotNull`. Will `city=""` be detected? No, because `@Valid` is missing to cascade into `Address`.

**Exercise 5.** When calling `validator.validate(dto, OnUpdate.class)`, do constraints declaring only `Default` run automatically? Not automatically, unless corresponding group/sequence relationships are defined.

**Exercise 6.** Design `@ValidPeriod` checking `startDate <= endDate`. State a reasonable target: `TYPE`, with a validator receiving the DTO containing both dates; allow or reject null by explicit convention, and combine `@NotNull` for required fields.

**Exercise 7.** Why can `@Valid @RequestBody` return 400 before entering the controller? Spring MVC invokes the validation provider after DTO deserialization; constraint failures lead to a request argument error and the default HTTP error handling mechanism.

## 14. Key Takeaways in Practice

- Jakarta Validation provides **an annotation-based declarative constraint model**, while the provider executes the rules.
- Constraints do not run on their own; there must be an explicit `Validator` call or framework integration point.
- Clearly separate: **presence** (`@NotNull`/`@NotBlank`), **valid value** (`@Size`/`@Pattern`/`@Positive`), and **business relationships**.
- `@Valid` cascades into child beans; constraints on generic type arguments validate each element.
- `groups` control which set of constraints runs; `Default` does not automatically accompany every other group.
- Custom constraints must have `@Constraint`, `message`, `groups`, `payload`, and a compatible validator when custom checking code is needed.
- With Spring Boot 3+, use `jakarta.validation` and an appropriate provider dependency; distinguish JSON/binding errors, Jakarta Validation errors, and business errors.

### References

- Jakarta Validation 3.1 Specification: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation API, `@Constraint`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraint
- Hibernate Validator 8 Reference Guide: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework — Validation in Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — `@RequestBody`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
