# Validating Required Fields, Cross-Field Constraints, and Localized Messages in Spring Data REST

## Objective

After this lesson, you will be able to declare required fields with Bean Validation; validate relationships across multiple fields in the same entity; trigger validators at the exact point Spring Data REST creates or updates a resource; validate nested objects; and return error messages in the client's language.

## 1. Where Does Validation Sit in the Data Write Flow?

A write request passes through multiple steps: Spring Data REST receives the request, converts the body into a domain object, executes pre-save processing steps, calls the repository, and finally the persistence provider writes the data.

Validation should run before data is persisted so invalid requests are rejected at the API boundary. Rules can be divided into three groups:

- **Per-field constraints:** name must not be blank, email must be properly formatted, quantity must be positive.
- **Cross-field constraints:** end date must not precede start date, delivery date must fall within an allowed window, or one field is required when another field has a certain value.
- **System-dependent business rules:** whether an email is already in use, whether the user has permission to create a record in that tenant, or whether a state transition is allowed.

Jakarta Bean Validation fits the first two groups because rules can be declared directly on the domain model and reused. The third group typically requires a service or validator that can access repositories and the security context. Do not place side effects such as sending emails or writing to the database inside a `ConstraintValidator`.

## 2. Adding Bean Validation and Declaring Required Fields

With Spring Boot 3 and later, use the `jakarta.validation` dependency `spring-boot-starter-validation`. Annotations belong to the `jakarta.validation` namespace:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Example Booking entity:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;
import java.time.LocalDate;

@Entity
public class Booking {

    @Id
    @GeneratedValue
    private Long id;

    @NotBlank(message = "{booking.customer.required}")
    @Size(max = 120, message = "{booking.customer.size}")
    private String customerName;

    @NotNull(message = "{booking.startDate.required}")
    private LocalDate startDate;

    @NotNull(message = "{booking.endDate.required}")
    private LocalDate endDate;

    @NotNull(message = "{booking.amount.required}")
    @Positive(message = "{booking.amount.positive}")
    private BigDecimal amount;

    protected Booking() {
    }

    // Constructor, getters, and setters
}
```

Some commonly used annotations:

| Annotation | Meaning | Notes |
| --- | --- | --- |
| `@NotNull` | Value must not be null | Does not check empty strings or whitespace |
| `@NotBlank` | String must have at least one non-whitespace character | Used for `String` or `CharSequence` |
| `@NotEmpty` | String, collection, map, or array must not be empty | Does not replace validating individual element contents |
| `@Size(min, max)` | Limits length or number of elements | Null values are usually still valid; combine with `@NotNull` if needed |
| `@Email` | Checks email address shape | Does not prove the mailbox exists; combine with `@NotBlank` if email is required |
| `@Positive`, `@Min`, `@Max` | Numeric limits | Choose numeric types and bounds appropriate for the domain |
| `@Past`, `@Future` | Date/time constraints relative to now | Check time zone and reference instant if the domain is time-sensitive |

For example, `@Email` alone does not make email a required field because null can be treated as valid for this constraint. If email is required, combine:

```java
@NotBlank(message = "{customer.email.required}")
@Email(message = "{customer.email.invalid}")
private String email;
```

Do not use a single annotation to represent multiple distinct meanings. Separating rules makes error messages accurate and helps clients know what to fix.

## 3. Registering Validators into the Spring Data REST Lifecycle

Spring Data REST emits repository events around creation, updates, association changes, and deletion. Two common points to validate entities are:

- `beforeCreate`: before saving a new entity created via a collection resource.
- `beforeSave`: before saving an entity being updated via an item resource.

Spring Data REST supports two ways to attach validators:

1. Naming the bean after the pattern `<event><DomainType>Validator`, e.g., `beforeCreateBookingValidator`.
2. Manually registering the validator with `ValidatingRepositoryEventListener` in `RepositoryRestConfigurer`.

Example registering Bean Validation for both creation and updates:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.event.ValidatingRepositoryEventListener;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class RepositoryValidationConfiguration
        implements RepositoryRestConfigurer {

    private final LocalValidatorFactoryBean beanValidator;

    public RepositoryValidationConfiguration(
            LocalValidatorFactoryBean beanValidator) {
        this.beanValidator = beanValidator;
    }

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener listener) {

        listener.addValidator("beforeCreate", beanValidator);
        listener.addValidator("beforeSave", beanValidator);
    }
}
```

In Spring Boot, a Bean Validation provider is typically supplied via the validation starter dependency. If the application does not yet have a `LocalValidatorFactoryBean` bean, you can declare one:

```java
@Bean
LocalValidatorFactoryBean beanValidator(MessageSource messageSource) {
    LocalValidatorFactoryBean validator = new LocalValidatorFactoryBean();
    validator.setValidationMessageSource(messageSource);
    return validator;
}
```

Place the `@Bean` method in a `@Configuration` class and inject the same validator into the configurer. If the application already has a validator configured by Spring Boot, use the existing bean and only configure the message source when needed. Avoid creating unnecessary duplicate validators or registering the same validator multiple times for the same event.

You can use the `beforeLinkSave` event name when you need to validate an association before saving a link. Other events such as `afterCreate`, `afterSave`, `beforeDelete`, and `afterDelete` serve different stages of the resource lifecycle; validators meant to reject data should generally run on pre-save events.

Note: declaring `@NotBlank` on an entity does not automatically guarantee that every write path in the application passes through the Spring Data REST validation listener. If a service or custom controller writes directly via the repository, invoke Bean Validation or apply validation in that service/controller accordingly.

## 4. Validating Nested Objects with @Valid

If an entity contains a nested object, constraints on the child object are only checked recursively when cascade validation is enabled with `@Valid`.

Example:

```java
import jakarta.persistence.Embeddable;
import jakarta.persistence.Embedded;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

@Embeddable
public class ContactDetails {

    @NotBlank(message = "{contact.phone.required}")
    @Pattern(
        regexp = "^[0-9+() -]{8,20}$",
        message = "{contact.phone.invalid}"
    )
    private String phone;

    @NotBlank(message = "{contact.country.required}")
    private String country;

    // Getters and setters
}

@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    @NotNull(message = "{customer.contact.required}")
    @Valid
    @Embedded
    private ContactDetails contactDetails;

    // Constructor, getters, and setters
}
```

Both annotations have distinct roles:

- `@NotNull` on `contactDetails` requires the child object to be present.
- `@Valid` tells the validator to continue validating constraints inside `ContactDetails`.

If you only have `@Valid` without `@NotNull`, a null child object has no contents to inspect and is not automatically treated as an error. For collections, you can use container element validation such as `List<@Valid LineItem>` to validate each element; add `@NotEmpty` if the collection must contain at least one element.

## 5. Cross-Field Constraints with Class-Level Constraints

Annotations such as `@NotNull`, `@Positive`, or `@Size` typically validate individual properties. When a rule depends simultaneously on multiple properties, create a custom class-level constraint.

For example, requiring `endDate` to be on or after `startDate`. First, declare the annotation:

```java
import jakarta.validation.Constraint;
import jakarta.validation.Payload;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Constraint(validatedBy = BookingPeriodValidator.class)
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ValidBookingPeriod {

    String message() default "{booking.period.invalid}";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

Next, implement the validator:

```java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class BookingPeriodValidator
        implements ConstraintValidator<ValidBookingPeriod, Booking> {

    @Override
    public boolean isValid(
            Booking booking,
            ConstraintValidatorContext context) {

        if (booking == null
                || booking.getStartDate() == null
                || booking.getEndDate() == null) {
            // @NotNull on each field is responsible for null checking.
            return true;
        }

        boolean valid =
                !booking.getEndDate().isBefore(booking.getStartDate());

        if (!valid) {
            context.disableDefaultConstraintViolation();
            context.buildConstraintViolationWithTemplate(
                    context.getDefaultConstraintMessageTemplate())
                .addPropertyNode("endDate")
                .addConstraintViolation();
        }

        return valid;
    }
}
```

Attach the constraint to the entity:

```java
@Entity
@ValidBookingPeriod
public class Booking {

    @NotNull(message = "{booking.startDate.required}")
    private LocalDate startDate;

    @NotNull(message = "{booking.endDate.required}")
    private LocalDate endDate;

    // Properties, constructor, getters, and setters
}
```

The validator returns true if the date range is valid. When the end date is before the start date, it builds a violation attached to the `endDate` property so clients know which field to fix. Null fields are handled separately by `@NotNull` so no noisy duplicate date-range errors are generated.

This same technique can be used for:

- `password` and `confirmPassword` must match.
- `minimumPrice` must not exceed `maximumPrice`.
- Only require `companyTaxCode` when `customerType = COMPANY`.
- Effective date must fall within the contract term.

For rules requiring database queries or user permissions, use an appropriate Spring Validator/service instead of turning constraints into places that perform business logic with side effects.

## 6. Localized Validation Messages

Do not hardcode Vietnamese or English messages directly inside annotations if the API serves multiple locales. Use message keys:

```java
@NotBlank(message = "{booking.customer.required}")
private String customerName;
```

Place resource bundles at the classpath root. For example, `messages.properties` contains default messages:

```properties
booking.customer.required=Customer name is required.
booking.customer.size=Customer name must not exceed {max} characters.
booking.startDate.required=Start date is required.
booking.endDate.required=End date is required.
booking.amount.required=Amount is required.
booking.amount.positive=Amount must be greater than zero.
booking.period.invalid=End date must be on or after start date.
contact.phone.required=Phone number is required.
contact.phone.invalid=Phone number format is invalid.
contact.country.required=Country is required.
customer.contact.required=Contact details are required.
```

Create a `messages_vi.properties` file for Vietnamese:

```properties
booking.customer.required=Vui lòng nhập tên khách hàng.
booking.customer.size=Tên khách hàng không được vượt quá {max} ký tự.
booking.startDate.required=Vui lòng nhập ngày bắt đầu.
booking.endDate.required=Vui lòng nhập ngày kết thúc.
booking.amount.required=Vui lòng nhập số tiền.
booking.amount.positive=Số tiền phải lớn hơn 0.
booking.period.invalid=Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.
contact.phone.required=Vui lòng nhập số điện thoại.
contact.phone.invalid=Số điện thoại không đúng định dạng.
contact.country.required=Vui lòng nhập quốc gia.
customer.contact.required=Vui lòng cung cấp thông tin liên hệ.
```

You can add `messages_en.properties` if you want to manage English separately. Spring Boot auto-configures `MessageSource` when a default `messages.properties` bundle exists; configure the basename if using a different name or location:

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

Spring Boot integrates the application `MessageSource` with Bean Validation message resolution. In Spring applications not using this Boot configuration, `LocalValidatorFactoryBean.setValidationMessageSource(messageSource)` lets you use Spring's `MessageSource` instead of Bean Validation's default bundle.

If the application's locale resolver takes the language from HTTP `Accept-Language`, clients can request Vietnamese messages:

```http
POST /bookings
Content-Type: application/json
Accept: application/hal+json
Accept-Language: vi
```

The actual locale also depends on the locale resolver and message source configuration. Verify whether requests passing through Spring MVC/Spring Data REST use the expected locale; do not infer language solely from JSON content.

In message templates, `{max}`, `{min}`, and other constraint attributes are interpolated to their respective values. Preserve placeholders across translation files so messages continue displaying exact limits.

## 7. How Does the API Return Validation Errors?

When a validator is registered for an event and data is invalid, Spring Data REST rejects the operation before saving. For Spring `Errors`-style validators, errors are wrapped in `RepositoryConstraintViolationException`; this exception retains the error list for the REST layer to build a response.

Validation failures are typically returned as request errors, commonly `400 Bad Request`. The exact body structure depends on the Spring Data REST version, media type, exception handlers, and application configuration. Inspect the actual response instead of assuming every version produces the exact same JSON error schema.

Example of a client sending an invalid date range:

```http
POST /bookings
Content-Type: application/json
Accept: application/hal+json
Accept-Language: vi

{
  "customerName": "Ada",
  "startDate": "2026-06-20",
  "endDate": "2026-06-10",
  "amount": 150
}
```

The expected result is that the request is rejected and the `booking.period.invalid` message is resolved according to the current locale. No new Booking is saved.

For public APIs, keep messages concise, actionable, and free of stack traces, SQL, table names, sensitive data, or internal details. If clients need to handle errors via stable codes, return a separate error code rather than forcing clients to parse translated prose.

## 8. Testing Validation on POST and PATCH/PUT

Test at least the following cases:

1. Omit a required field such as `customerName`; confirm `@NotBlank` or `@NotNull` catches the error.
2. Send a whitespace-only string; confirm `@NotBlank` rejects it.
3. Send a negative number for `amount`; confirm `@Positive` rejects it.
4. Send an end date before the start date; confirm the class-level constraint catches the cross-field error.
5. Omit the entire `contactDetails` object; confirm `@NotNull` on the parent object catches the error.
6. Send `contactDetails` missing `phone`; confirm `@Valid` triggers nested validation.
7. Send the same payload with `Accept-Language: vi` and `Accept-Language: en`; confirm the right message bundle is selected.
8. Update a resource with `PATCH` or `PUT`; confirm the validator is attached to `beforeSave` and the post-binding entity state still satisfies all rules.

Example using curl to verify Vietnamese messages:

```bash
curl -i -X POST http://localhost:8080/bookings \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -H "Accept-Language: vi" \
  -d '{
    "customerName": "Ada",
    "startDate": "2026-06-20",
    "endDate": "2026-06-10",
    "amount": 150
  }'
```

With `PATCH`, Spring Data REST applies the body onto the existing resource and then emits the save event. Inspect the post-binding state so you do not mistakenly assume every field omitted from the payload becomes null. If different rules are needed between create and update, consider validation groups or separate validators for `beforeCreate` and `beforeSave`.

## 9. Distinguishing Application Validation from Database Constraints

Bean Validation improves error messages and blocks invalid data before saving, but it does not replace database constraints.

For example, checking whether an email already exists by querying the repository before saving helps return a friendly message. However, two concurrent requests can still both pass the check. Only a database unique constraint serves as the final safeguard for uniqueness.

You should combine:

- Bean Validation for required fields, formats, limits, and cross-field constraints.
- Service/domain logic for rules depending on existing data or the current user.
- Database constraints for integrity that must hold even under concurrent requests or non-API write paths.
- Exception handling to translate persistence errors into stable responses without leaking internal details.

## 10. Common Configuration Mistakes

**Annotations are present but requests are still saved**

Check whether the validation starter/provider is on the classpath; whether the validator is registered with Spring Data REST on the right event; whether the bean name matches the convention if using name-based wiring; or whether the configurer called `addValidator`.

**Creation is validated but updates are not**

The validator may only be registered on `beforeCreate`. Add the validator to `beforeSave` if rules must also apply to PUT/PATCH.

**Nested objects are not validated**

Add `@Valid` on the property or container element that needs cascading. If the object is required, add `@NotNull` separately.

**Cross-field errors do not appear**

Ensure the constraint is placed at class level with `@Target(ElementType.TYPE)`, the validator is registered via Bean Validation, and the class-level annotation is actually present on the entity being validated.

**Messages only show keys or do not switch languages**

Check that the default bundle file exists, basename configuration, UTF-8 encoding, exact message key spelling, and request locale. If using Spring `MessageSource` directly, configure `LocalValidatorFactoryBean.setValidationMessageSource(...)`.

**Custom endpoints do not run Spring Data REST validators**

The repository event listener only handles operations going through Spring Data REST's event pipeline. For custom controllers/services, trigger validation with `@Valid`, `@Validated`, or invoke the appropriate validator directly in that flow.

## Summary

- Use `@NotBlank`, `@NotNull`, `@Size`, `@Email`, and appropriate constraints to validate individual fields.
- Use class-level constraints with `ConstraintValidator` for rules spanning multiple fields; attach violations to the relevant property so clients can easily fix them.
- Use `@Valid` to cascade validation into nested objects; combine with `@NotNull` if the child object is required.
- Register validators with Spring Data REST via bean names like `beforeCreateBookingValidator` or via `RepositoryRestConfigurer` and `ValidatingRepositoryEventListener`.
- Attach validators to both `beforeCreate` and `beforeSave` if rules apply to both creation and updates.
- Use message keys and locale-specific resource bundles; verify `Accept-Language`, `MessageSource`, and the locale resolver.
- Combine application validation with business rules and database constraints to ensure valid data across all write paths.

## References

- [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST — RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [Spring Boot — Internationalization](https://docs.spring.io/spring-boot/reference/features/internationalization.html)
- [RepositoryConstraintViolationException API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/RepositoryConstraintViolationException.html)
