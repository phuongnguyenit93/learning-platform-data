# Declaring Jakarta Bean Validation and Verifying Where It Actually Triggers

Jakarta Bean Validation allows you to declare data validation rules directly on the model using annotations such as **`@NotNull`**, **`@NotBlank`**, **`@Email`**, **`@Size`**, or **`@Positive`**. However, annotations only describe constraints. For constraints to be enforced, the application must have a Bean Validation provider and a processing flow that actually invokes the validator.

With Spring Data REST, you must clearly identify which trigger point a request passes through. You can use a validator attached to repository events **`beforeCreate`** or **`beforeSave`**. If using Spring Data JPA, the persistence provider can also trigger Bean Validation at the **`PrePersist`** and **`PreUpdate`** lifecycle phases. These two mechanisms are independent and execute at different times.

## 1. Adding a Jakarta Bean Validation Provider

If using Spring Boot, add the validation starter dependency to get the API and implementation provider:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

For applications not using Spring Boot, declare the Jakarta Validation API and a compatible provider, such as Hibernate Validator. Having only the annotation API without a provider cannot perform constraint checking.

In Spring Framework, **`LocalValidatorFactoryBean`** bootstraps the Bean Validation provider and simultaneously adapts to both interfaces:

- **`jakarta.validation.Validator`**
- **`org.springframework.validation.Validator`**

The second point is important because Spring Data REST registers validators through the **`org.springframework.validation.Validator`** contract.

## 2. Declaring Constraints on the Entity

Example Person entity:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @NotBlank(message = "Name must not be blank")
    @Size(max = 80, message = "Name must be at most 80 characters")
    private String name;

    @NotBlank(message = "Email is required")
    @Email(message = "Email format is invalid")
    private String email;

    @Positive(message = "Age must be greater than zero")
    private Integer age;

    // getters and setters
}
~~~

Some commonly used constraints:

| Annotation | Rule |
|---|---|
| **`@NotNull`** | Value must not be null |
| **`@NotBlank`** | String must not be null, empty, or whitespace-only |
| **`@NotEmpty`** | String, collection, map, or array must not be null and must have elements |
| **`@Size(min, max)`** | Limits length or number of elements |
| **`@Email`** | String value must have a valid email format according to the provider |
| **`@Min`** / **`@Max`** | Limits integer or numeric values |
| **`@Positive`** / **`@PositiveOrZero`** | Value must be positive or non-negative |
| **`@Pattern`** | String value must match a regular expression |

Combine constraints according to business meaning. For example, **`@Email`** allows null, so if email is required, combine it with **`@NotBlank`** or **`@NotNull`**.

Place annotations on fields or getters following a consistent strategy. With JPA, annotation placement also relates to how the entity accesses fields/properties. Avoid declaring the same constraint on both the field and getter if that causes the validator to check it twice.

## 3. Cascade Validation with @Valid

Constraints on an object do not automatically mean nested objects inside it are checked as well. Use **`@Valid`** on the property that needs cascade validation.

Example with Address as an embeddable of Person:

~~~java
import jakarta.persistence.Embeddable;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@Embeddable
public class Address {

    @NotBlank
    private String city;

    @Size(max = 120)
    private String street;

    // getters and setters
}
~~~

~~~java
import jakarta.persistence.Embedded;
import jakarta.validation.Valid;

@Entity
public class Person {

    // Other properties...

    @Embedded
    @Valid
    private Address address;

    // getters and setters
}
~~~

When Person is validated, **`@Valid`** tells the validator to continue checking the constraints of Address. Without **`@Valid`**, constraints inside the nested object may not be cascaded from that Person validation pass.

For JPA entity associations, note the specific Jakarta Persistence rule: the validation lifecycle by default does not cascade to entity associations just because **`@Valid`** is placed on the association. Embeddables require **`@Valid`** to be cascaded. If you need to validate related entities, design an appropriate business flow or validator and avoid accidentally loading lazy associations.

## 4. Distinguishing Constraint Declarations from Trigger Points

This is the most important point when verifying validation:

- **`@NotBlank`**, **`@Email`**, and other constraints only describe conditions.
- **`jakarta.validation.Validator`** executes the constraints when invoked.
- **`LocalValidatorFactoryBean`** bridges Jakarta Bean Validation with Spring Validator.
- Spring Data REST invokes validators attached to repository events.
- The JPA provider can invoke Bean Validation during the persistence lifecycle if integration is enabled and a provider is present.

Therefore, do not conclude that validation is working merely because the entity has annotations or the application starts up successfully.

## 5. Triggering Validation on Spring Data REST Repository Events

Spring Data REST provides **`ValidatingRepositoryEventListener`** to invoke Spring Validators on corresponding events. A simple approach is naming the bean with the event prefix and domain type.

Example registering validators for Person on create and update:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class RestValidationConfiguration {

    @Bean
    public LocalValidatorFactoryBean beforeCreatePersonValidator() {
        return new LocalValidatorFactoryBean();
    }

    @Bean
    public LocalValidatorFactoryBean beforeSavePersonValidator() {
        return new LocalValidatorFactoryBean();
    }
}
~~~

Spring Data REST recognizes the bean names:

- **`beforeCreatePersonValidator`**: runs before a new Person entity is saved.
- **`beforeSavePersonValidator`**: runs before an existing Person entity is saved.

**`LocalValidatorFactoryBean`** implements Spring Validator, so Spring Data REST can invoke it. When invoked, it executes Jakarta Bean Validation annotations on the object and translates violations into Spring Validation errors.

You can register the same validator for multiple events via manual configuration instead of bean naming.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfigurer;
import org.springframework.data.rest.core.event.ValidatingRepositoryEventListener;
import org.springframework.validation.Validator;

@Configuration
public class RestValidationConfiguration
        implements RepositoryRestConfigurer {

    private final Validator validator;

    public RestValidationConfiguration(Validator validator) {
        this.validator = validator;
    }

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener listener) {
        listener.addValidator("beforeCreate", validator);
        listener.addValidator("beforeSave", validator);
    }
}
~~~

Choose a registration approach suitable for your application configuration. If using a bean name prefix, verify the bean has the exact name and is managed by Spring. If registering manually, verify **`configureValidatingRepositoryEventListener`** is called and the validator is added to the right events.

## 6. Mapping Requests to Corresponding Events

Different REST operations emit different repository events:

| Operation | Pre-processing Event | Meaning |
|---|---|---|
| **POST /people** | **`beforeCreate`** | Validate new entity before saving |
| **PUT /people/{id}** | **`beforeSave`** | Validate existing entity before saving |
| **PATCH /people/{id}** | **`beforeSave`** | Validate existing entity before saving |
| Updating an association resource | **`beforeLinkSave`** | Event before saving a link |
| **DELETE /people/{id}** | **`beforeDelete`** | Event before deleting |

The event name used when registering a validator is the prefix part of the bean name, such as **`beforeCreate`** and **`beforeSave`**. You can attach separate validators per domain type by appending the entity name to the bean name.

A GET request only reads data and does not pass through these entity-saving events. If you need to validate input data for a search endpoint, configure an appropriate validation mechanism for that endpoint.

## 7. Distinguishing Repository Events from JPA Lifecycle Validation

When using Spring Data JPA with a provider that integrates Jakarta Bean Validation, the persistence provider can automatically validate entities at lifecycle phases:

- **`PrePersist`**: before inserting a new entity.
- **`PreUpdate`**: before updating an entity.
- **`PreRemove`**: only when a validation group is configured for remove; by default, do not assume delete operations are validated.

This JPA mechanism can apply to persist/update operations from REST, services, or batch jobs because it runs at the persistence layer. However, it is not a Spring Data REST repository event.

| Mechanism | Trigger Point | Scope |
|---|---|---|
| Spring Data REST validator | **`beforeCreate`**, **`beforeSave`**, registered events | Operations going through the REST exporter |
| JPA Bean Validation | **`PrePersist`**, **`PreUpdate`** | Persistence operations through JPA when integration is active |
| Spring MVC **`@Valid`** | After binding request body to controller parameter | Controller endpoints with validation declared |
| Method validation with **`@Validated`** | When calling a method through a validation proxy | Methods/services configured for method validation |

A validator working at one point does not prove the remaining points also work. For example, JPA lifecycle validation may block a flush while a Spring Data REST event validator has not yet been registered.

If the application does not use JPA, you cannot rely on **`PrePersist`** or **`PreUpdate`**; use Spring Data REST validators or the validation mechanism of the corresponding persistence module.

## 8. Using @Valid in Custom Controllers

If the application has custom Spring MVC controllers alongside repository resources, you can trigger validation for a request body with **`@Valid`**:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PersonController {

    @PostMapping("/custom-people")
    public ResponseEntity<Void> create(
            @Valid @RequestBody PersonRequest request) {
        // Process validated request
        return ResponseEntity.noContent().build();
    }
}
~~~

In the example, Spring MVC validates **`PersonRequest`** after binding JSON into the object. This is a controller trigger point, not a validator configuration for Spring Data REST repository events.

For method validation on services, configure Spring's method validation and use **`@Validated`** on the appropriate bean. Do not confuse **`@Valid`** for cascading objects with **`@Validated`** for enabling method validation.

## 9. Verifying That Validation Actually Runs

Verify using HTTP integration tests and check both the response and database state.

### Testing POST — beforeCreate

Send data violating constraints:

~~~http
POST /people
Content-Type: application/json
Accept: application/hal+json
~~~

~~~json
{
  "name": "   ",
  "email": "not-an-email",
  "age": -2
}
~~~

If **`beforeCreatePersonValidator`** is registered properly, the request must be rejected by the constraints. Check the validation error response and verify no invalid Person was saved.

Then send valid data:

~~~json
{
  "name": "An Nguyen",
  "email": "an@example.com",
  "age": 28
}
~~~

A valid request must create the resource according to the repository contract.

### Testing PUT or PATCH — beforeSave

First create a valid Person, then send a PUT or PATCH that violates a constraint, such as an invalid email format. Confirm **`beforeSavePersonValidator`** runs and invalid data is not saved.

### Testing the JPA lifecycle separately

If you want to verify the JPA provider, call repository save in a test and force a flush:

~~~java
@Test
void invalidEntityIsRejectedAtJpaLifecycle() {
    Person person = new Person();
    person.setName(" ");
    person.setEmail("invalid");

    assertThrows(
        ConstraintViolationException.class,
        () -> {
            personRepository.saveAndFlush(person);
        }
    );
}
~~~

This test verifies the path through the JPA lifecycle when the provider is configured. It does not replace HTTP tests for Spring Data REST events.

### Checking actual events

You can place breakpoints or logs in the validator to confirm:

1. The request enters the right endpoint.
2. The corresponding event is emitted.
3. The validator is called with the right domain object.
4. Constraint violations are recorded.
5. The repository does not save the invalid entity.

If you only see the database reporting a NOT NULL or unique constraint error, that is not yet proof that Jakarta Bean Validation was triggered. It may be a persistence/database error occurring later.

## 10. Validation Groups and Error Messages

Jakarta Bean Validation supports validation groups to apply different rules depending on context:

~~~java
public interface OnCreate {
}

public interface OnUpdate {
}
~~~

~~~java
@NotBlank(groups = { OnCreate.class, OnUpdate.class })
private String name;

@NotNull(groups = OnCreate.class)
private String externalCode;
~~~

By default, the validator runs the **`Default`** group. If using custom groups, you must configure the validator or invocation flow to actually request those groups; merely declaring **`groups`** on annotations is not enough.

Error messages can be placed directly in annotations or use a message bundle:

~~~java
@NotBlank(message = "{person.name.required}")
private String name;
~~~

Example **`ValidationMessages.properties`** file:

~~~properties
person.name.required=Name is required.
person.email.invalid=Please enter a valid email address.
~~~

With Spring Data REST event validators, errors from Spring Validator are represented via **`Errors`** and may raise **`RepositoryConstraintViolationException`**. The final response format also depends on exception handlers and application configuration; integration tests should verify the actual contract that clients receive.

## 11. Common Pitfalls and How to Handle Them

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Annotations present but POST still saves invalid data | Missing provider or validator not attached to **`beforeCreate`** | Check dependencies and bean name/event registration |
| POST is blocked but PUT still saves invalid data | Validator only registered for **`beforeCreate`** | Also register **`beforeSave`** |
| REST event validation does not run when calling service directly | Spring Data REST repository events are not emitted on that call path | Check JPA lifecycle or invoke validator in the service |
| Nested object is not checked | Missing **`@Valid`** on the property needing cascade | Add **`@Valid`** and check the cascade path |
| JPA does not cascade validation to entity associations | JPA lifecycle rules do not cascade validation across entity associations | Validate associations in appropriate business logic; do not rely on default cascade |
| Constraint groups are not applied | Validator is running the **`Default`** group | Configure the requested groups at the exact invocation point |
| Only database constraints catch errors | Bean Validation has not run or constraints are not equivalent | Check provider, events, annotations, and test the validator independently |

## 12. Verification Checklist

- Dependencies include the Jakarta Validation API and a compatible provider.
- Entities have constraints matching business rules.
- Nested objects have **`@Valid`** when cascade is needed.
- Spring Data REST has properly named validator beans or manual registration.
- **`beforeCreate`** is tested for POST.
- **`beforeSave`** is tested for PUT/PATCH.
- If updating relationships, consider **`beforeLinkSave`**.
- If using JPA, test **`PrePersist`** and **`PreUpdate`** separately.
- Invalid request tests must be rejected before invalid data is persisted.
- Valid request tests must succeed.
- Verify via logs, breakpoints, or integration tests which exact validator ran.

Official references:

- [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Framework — Java Bean Validation and LocalValidatorFactoryBean](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Jakarta Persistence — Automatic Bean Validation lifecycle events](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html)
- [Jakarta Validation Specification](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.pdf)
