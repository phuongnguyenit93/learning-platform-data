# Validation on @Argument

In Spring for GraphQL, GraphQL operation arguments are checked across multiple layers. GraphQL validates syntax, schema, and data types; Spring binds values to Java parameters; Bean Validation checks rules on input objects; and the service/domain layer checks conditions depending on existing data, state, and access permissions.

With annotated controllers, the **@Argument** annotation receives field arguments. When an argument is an input object, you can combine **@Valid** with Jakarta Bean Validation to check the DTO before the resolver runs business logic. This lesson presents how to configure the validator, declare constraints, validate nested objects and collections, choose validation groups, handle errors, and test with GraphQlTester.

## 1. Layers of input checking

A GraphQL request passes through the following stages:

1. **Parse:** the parser reads the GraphQL document. Syntax errors are rejected.
2. **Validate document:** GraphQL checks whether fields, arguments, and selection sets exist in the schema.
3. **Input coercion:** GraphQL checks scalars, enums, lists, nullability, and input object structure against the SDL.
4. **Argument binding:** Spring converts coerced values into the Java types required by the resolver.
5. **Bean Validation:** Jakarta Validation checks constraints on Java objects.
6. **Business validation:** the service/domain checks existing data, state, quotas, and permissions.

SDL example:

~~~graphql
input RegisterCustomerInput {
    displayName: String!
    email: String!
    age: Int!
    address: AddressInput!
    tags: [String!]
}

input AddressInput {
    city: String!
    postalCode: String
}

type Customer {
    id: ID!
    displayName: String!
    email: String!
}

type Mutation {
    registerCustomer(input: RegisterCustomerInput!): Customer!
}
~~~

SDL guarantees non-null fields have values and those values have the right types. However, SDL cannot express every rule, such as email having a valid format, displayName being at least two characters long, or age being 18 or above. These rules fit Bean Validation.

| Layer | Example | Handling component |
| --- | --- | --- |
| GraphQL schema/coercion | Missing non-null input or invalid enum | GraphQL engine |
| Java binding | Unable to instantiate DTO or convert type | GraphQlArgumentBinder |
| Bean Validation | Malformed email or whitespace-only name | Jakarta Bean Validation |
| Business validation | Email already exists in database | Service/domain |

Flow diagram:

~~~mermaid
flowchart TD
    A["GraphQL request"] --> B["Parse and validate document"]
    B --> C["Coerce argument against SDL"]
    C --> D["Bind argument into Java DTO"]
    D --> E["Bean Validation"]
    E --> F{"Constraints valid?"}
    F -->|Yes| G["Invoke annotated controller"]
    F -->|No| H["ConstraintViolationException"]
    H --> I["GraphQL exception handling"]
    I --> J["Response with errors"]
    G --> K["Service and business rules"]
~~~

Distinguishing these stages helps choose the right fix. Bean Validation cannot fix a syntactically invalid operation or a field that does not exist in the SDL.

## 2. Adding the dependency and configuring the Validator

With Spring Boot, add the validation starter to get the Jakarta Validation API and implementation:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Spring Boot usually auto-configures a Validator when the dependency is present. AnnotatedControllerConfigurer uses the Validator bean to check parameters marked with @Valid or @Validated.

If the application does not use auto-configuration, you can declare LocalValidatorFactoryBean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration(proxyBeanMethods = false)
public class ValidationConfiguration {

    @Bean
    LocalValidatorFactoryBean validator() {
        return new LocalValidatorFactoryBean();
    }
}
~~~

Spring Boot 3 and above applications use the jakarta.validation namespace. Do not mix legacy javax.validation imports with jakarta.validation in the same configuration.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
~~~

Simply placing @Valid in source code is not enough if the application context has no validation provider or Validator bean. When validation does not run, check dependencies and configuration first.

## 3. Declaring constraints on an input DTO

GraphQL input objects are commonly mapped into Java records or classes. Example:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.util.List;

public record AddressInput(
        @NotBlank
        @Size(max = 80)
        String city,

        @Pattern(
                regexp = "[0-9A-Za-z -]{3,12}",
                message = "Postal code format is invalid"
        )
        String postalCode
) {
}

public record RegisterCustomerInput(
        @NotBlank
        @Size(min = 2, max = 80)
        String displayName,

        @NotBlank
        @Email
        @Size(max = 254)
        String email,

        @NotNull
        @Min(18)
        @Max(120)
        Integer age,

        @NotNull
        @Valid
        AddressInput address,

        @Size(max = 10)
        List<@NotBlank @Size(max = 30) String> tags
) {
}
~~~

Main constraints:

| Constraint | Meaning |
| --- | --- |
| @NotNull | Value must not be null |
| @NotBlank | String must not be null, empty, or whitespace-only |
| @NotEmpty | String, collection, map, or array must not be empty |
| @Size | Limits string length or collection size |
| @Email | Checks basic email format |
| @Min, @Max | Limits numeric values |
| @Pattern | Validates a string against a regular expression |
| @Valid | Triggers cascade validation on nested objects |

With records, constraints placed on record components are checked by Jakarta Bean Validation via the corresponding components. With regular classes, constraints can be placed on fields or getters according to Bean Validation's access strategy.

Do not use primitive types for input fields that can be omitted or receive null. Integer can represent a value that has not been provided; int cannot.

## 4. Enabling validation with @Valid on @Argument

Place @Valid on the @Argument parameter to instruct Spring for GraphQL to validate the bound object before calling the method:

~~~java
import jakarta.validation.Valid;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class CustomerMutationController {

    private final CustomerService customerService;

    public CustomerMutationController(CustomerService customerService) {
        this.customerService = customerService;
    }

    @MutationMapping
    public Customer registerCustomer(
            @Argument("input") @Valid RegisterCustomerInput input) {
        return customerService.register(input);
    }
}
~~~

When the input argument is bound into RegisterCustomerInput, Bean Validation checks the constraints before the controller method executes. If any constraint is not satisfied, Spring for GraphQL raises ConstraintViolationException. Neither the resolver nor the service is called.

For example, suppose a client sends input with an invalid email, age under 18, and a whitespace-only city. The request may still be valid according to the SDL structure, but Bean Validation will reject its content.

## 5. Distinguishing @Valid and @Validated

The two annotations are related but serve different purposes:

| Annotation | Role |
| --- | --- |
| jakarta.validation.Valid | Triggers cascade validation under the default group |
| org.springframework.validation.annotation.Validated | Allows selecting validation groups or group sequences; also used in method validation |

For simple input objects, use @Valid:

~~~java
@MutationMapping
public Customer registerCustomer(
        @Argument("input") @Valid RegisterCustomerInput input) {
    return customerService.register(input);
}
~~~

When selecting a group is required, you can use @Validated on the argument parameter according to Spring for GraphQL's validation mechanism:

~~~java
@MutationMapping
public Customer createCustomer(
        @Argument("input") @Validated(OnCreate.class) CustomerInput input) {
    return customerService.create(input);
}
~~~

Validation groups are covered in a later section. Check the supported validation hints in the Spring for GraphQL version you are using. If a group on the parameter does not fit the current setup, you can separate DTOs for create/update or call Validator.validate(input, OnCreate.class) in the application service.

If placing constraints directly on a scalar parameter of the resolver, e.g., @Min on an Integer argument, that is method parameter validation. How it is triggered depends on the Spring Framework version and application configuration. In the traditional Spring AOP model, the controller/bean is typically marked with @Validated; newer Spring Framework versions have built-in method validation mechanisms. Avoid enabling multiple mechanisms simultaneously such that the same constraint runs repeatedly.

## 6. Validation for nested objects and collections

@Valid on the outermost input object does not automatically cascade into every child object. Mark @Valid on nested properties that need checking:

~~~java
public record AuthorInput(
        @NotBlank String name,
        @Email String email
) {
}

public record CreateBookInput(
        @NotBlank String title,
        @NotNull @Valid AuthorInput author
) {
}
~~~

@NotNull and @Valid have separate roles: @NotNull requires the child object to exist; @Valid requires checking the constraints inside the child object.

For collections containing input objects:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import java.util.List;

public record OrderLineInput(
        @NotBlank String productCode,
        @Min(1) @Max(100) Integer quantity
) {
}

public record CreateOrderInput(
        @NotEmpty
        @Size(max = 50)
        List<@NotNull @Valid OrderLineInput> lines
) {
}
~~~

For collections containing scalars, you can use container element constraints:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        List<@NotBlank @Size(max = 30) String> tags
) {
}
~~~

Distinguish:

- @Size on the list checks the number of elements.
- Constraints on List<@NotBlank String> check each string.
- @Valid on object elements triggers checking the properties inside.
- GraphQL list types and nullability are still checked earlier during input coercion.

## 7. Choosing constraints based on data semantics

Some commonly used built-in constraints:

| Constraint | Used for | Notes |
| --- | --- | --- |
| @NotNull | Required value | Only checks null |
| @NotBlank | Required string with non-whitespace characters | Does not apply to numbers or collections |
| @NotEmpty | Non-empty string, collection, map, or array | Does not check contents of each element |
| @Size | String length or collection size | Null is usually valid; combine with @NotNull if required |
| @Min, @Max | Integer bounds | Null is usually valid; combine with @NotNull if required |
| @DecimalMin, @DecimalMax | Decimal bounds | Useful with BigDecimal |
| @Positive, @PositiveOrZero | Positive or non-negative numbers | Combine with @NotNull if null is disallowed |
| @Email | Email format | Does not verify mailbox existence |
| @Pattern | String matching regular expression | Regex needs to be tested |
| @Past, @Future | Date/time relative to present | Choose appropriate date/time type and clock |

Example:

~~~java
public record RegisterAuthorInput(
        @NotBlank
        @Size(max = 120)
        String fullName,

        @NotBlank
        @Email
        String email,

        @NotNull
        @Min(18)
        @Max(120)
        Integer age
) {
}
~~~

A property may need multiple constraints at once:

~~~java
public record CreateBookInput(
        @NotBlank(message = "ISBN must not be blank")
        @Size(min = 10, max = 17, message = "ISBN length is invalid")
        @Pattern(
                regexp = "[0-9Xx-]+",
                message = "ISBN may only contain digits, X, or hyphens"
        )
        String isbn
) {
}
~~~

The format above only illustrates combining constraints; it does not replace ISBN-10/ISBN-13 verification algorithms and checksums. If true ISBN verification is needed, write a dedicated validator or use an appropriate domain library.

Notes on null:

- @NotBlank rejects null, empty strings, and whitespace-only strings.
- @Email usually accepts null; combine with @NotBlank if email is required.
- @Size usually accepts null; combine with @NotNull if the field is required.
- @Min and @Max usually accept null; combine with @NotNull if leaving it blank is not allowed.

SDL and Bean Validation can complement each other. For example, String! ensures a non-null value at the GraphQL layer, while @NotBlank also rejects empty or whitespace-only strings at the Java layer.

## 8. Using @Validated for validation groups

An input may be used across multiple operations with different requirements. For example, creating a customer requires an email; during a partial update, email may be omitted.

Declare groups:

~~~java
public interface OnCreate {
}

public interface OnUpdate {
}
~~~

Attach groups to constraints:

~~~java
public record CustomerProfileInput(
        @NotBlank(groups = {OnCreate.class, OnUpdate.class})
        @Size(max = 80, groups = {OnCreate.class, OnUpdate.class})
        String displayName,

        @NotBlank(groups = OnCreate.class)
        @Email(groups = {OnCreate.class, OnUpdate.class})
        String email
) {
}
~~~

Select the group on the argument parameter:

~~~java
import org.springframework.validation.annotation.Validated;

@MutationMapping
public Customer createCustomer(
        @Argument("input") @Validated(OnCreate.class) CustomerProfileInput input) {
    return customerService.create(input);
}

@MutationMapping
public Customer updateCustomer(
        @Argument("input") @Validated(OnUpdate.class) CustomerProfileInput input) {
    return customerService.update(input);
}
~~~

@Valid uses the default validation group. Spring's @Validated allows specifying a group or group sequence. A constraint attached only to OnCreate will not run automatically when the method selects OnUpdate.

The example above illustrates per-argument groups. Check the validation hints supported in the Spring for GraphQL version in use. If parameter-level groups do not fit the current setup, you can separate DTOs for create/update or call Validator.validate(input, OnCreate.class) in the application service.

Do not use groups to replace separate DTOs when create and update have very different input structures. Separate DTOs are usually easier to understand as rules grow complex.

## 9. Cross-field validation

Some rules require comparing multiple properties. For example, the end date must be after the start date.

Define the annotation:

~~~java
import jakarta.validation.Constraint;
import jakarta.validation.Payload;

import java.lang.annotation.Documented;
import java.lang.annotation.Retention;
import java.lang.annotation.Target;

import static java.lang.annotation.ElementType.TYPE;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

@Documented
@Target(TYPE)
@Retention(RUNTIME)
@Constraint(validatedBy = DateRangeValidator.class)
public @interface ValidDateRange {
    String message() default "endDate must be after startDate";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, DateRangeInput> {

    @Override
    public boolean isValid(
            DateRangeInput value,
            ConstraintValidatorContext context) {

        if (value == null
                || value.startDate() == null
                || value.endDate() == null) {
            return true;
        }

        return value.endDate().isAfter(value.startDate());
    }
}
~~~

Input record:

~~~java
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;

@ValidDateRange
public record DateRangeInput(
        @NotNull LocalDate startDate,
        @NotNull LocalDate endDate
) {
}
~~~

The class-level validator only checks the relationship between the two dates when both already have values. @NotNull is responsible for requiring each date. You can customize ConstraintValidatorContext to attach the violation to the endDate field rather than the whole object, helping the client display the error on the right input control.

## 10. Omitted, explicit null, and partial updates

With an update mutation, an omitted field and a field sent as explicit null can carry two different meanings:

- Omitted: the client does not request changing the property.
- Explicit null: the client wants to clear the value if business rules allow.
- Present value: the client wants to set a new value.

If a DTO uses regular nullable fields only, omitted and explicit null can both become null after binding. When you need to distinguish them, Spring for GraphQL provides ArgumentValue<T>:

~~~java
public record UpdateBookInput(
        ArgumentValue<String> description,
        ArgumentValue<Integer> pageCount
) {
}
~~~

The service checks isOmitted() to leave the property unchanged when the client did not send the field. If the field is sent as explicit null, check value() to apply the clear-or-reject policy.

Bean Validation should match the update semantics:

- @NotBlank on a field required for create may not fit an update field allowed to be omitted.
- @Size usually allows null, so it can check the value when the client actually sends it.
- If you need to validate a value only when present, you can handle it in the application service or use a validator supporting those semantics.
- Do not automatically turn omitted into a default value before knowing whether the business logic intends to keep or change it.

For complex partial updates, separate DTOs and per-state validation are usually easier to maintain than a single DTO shared across every mutation.

## 11. Distinguishing ConstraintViolationException, BindException, and GraphQL request errors

Input errors can occur at different stages:

| Error type | Timing | Example | How to handle |
| --- | --- | --- | --- |
| GraphQL parse/validation/coercion error | Before resolver runs | Syntax error, non-existent field, missing non-null input, invalid enum | Fix the operation or SDL |
| BindException | Spring cannot bind argument to target Java type | Constructor/property binding or type conversion fails | Fix DTO, Java type, or conversion |
| ConstraintViolationException | Argument was bound but violates Bean Validation | age = 16 when @Min(18) | Map to GraphQL validation error |
| Business exception | Inside service/domain | Email already exists or state does not allow | Handle according to business rules |

Do not lump BindException and ConstraintViolationException into one indistinguishable error. The two errors indicate two different problems: either the data could not be converted into a Java object, or the object was created but failed to satisfy constraints.

## 12. Converting validation failures into GraphQL errors

You can use @GraphQlExceptionHandler inside @ControllerAdvice to standardize ConstraintViolationException:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import jakarta.validation.ConstraintViolationException;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

import java.util.List;
import java.util.Map;

@ControllerAdvice
public class GraphQlValidationAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleConstraintViolation(
            ConstraintViolationException exception,
            DataFetchingEnvironment environment) {

        List<Map<String, String>> violations =
                exception.getConstraintViolations().stream()
                        .map(violation -> Map.of(
                                "field", violation.getPropertyPath().toString(),
                                "message", violation.getMessage()
                        ))
                        .toList();

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.BAD_REQUEST)
                .message("Invalid input data")
                .extensions(Map.of(
                        "code", "VALIDATION_FAILED",
                        "violations", violations
                ))
                .build();
    }
}
~~~

DataFetchingEnvironment helps GraphqlErrorBuilder preserve the path and source location of the executing field. The property path in violations describes the violating Java property; the GraphQL path identifies the failing field resolver. The two paths serve two different purposes.

Do not include invalid values in responses. Rejected values may contain emails, phone numbers, tokens, or sensitive data. Constraint messages should also be designed for clients and must not reveal internal structure.

You can handle BindException separately if needed:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.validation.BindException;
import org.springframework.web.bind.annotation.ControllerAdvice;

import java.util.Map;

@ControllerAdvice
public class GraphQlBindingAdvice {

@GraphQlExceptionHandler
public GraphQLError handleBindException(
        BindException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.BAD_REQUEST)
            .message("Unable to bind GraphQL argument")
            .extensions(Map.of("code", "ARGUMENT_BINDING_FAILED"))
            .build();
}
}
~~~

If using method validation for scalar parameters, the exception may differ depending on the mechanism and Spring Framework version. Handle the exact exception type your application actually raises.

## 13. Validation does not replace business rules and authorization

Bean Validation fits structural rules and local data limits:

- Required strings, length, and format.
- Numeric values within a range.
- Collection element counts.
- Simple relationships between properties.
- Contents of each element in a list.

Some rules require service/domain handling:

- Whether an email is already registered by another customer.
- Whether a product code exists and is still available for sale.
- Whether the current user has permission to create an order for the requested tenant.
- Whether the ordered quantity exceeds inventory at the moment of writing data.
- Whether the current state allows transitioning to the new state.

Do not call the database or external services from a constraint validator for every business rule if doing so makes validation unpredictable or introduces race conditions. For example, an email might not exist when checked, yet be registered by another request before the write transaction commits. Uniqueness rules still need to be protected by database unique constraints and conflict handling in the service.

Validation is also not authorization. A structurally valid input can still request an action that the current principal is not permitted to perform.

## 14. GraphQL errors, partial data, and null propagation

When validation fails in a resolver, GraphQL can return a response containing errors and a null value at the failing field. Other independent fields can still return data if the schema allows it.

If a field is declared nullable, the error may only turn that field into null. If the field or parent is non-null, null propagation can bubble up to the nearest nullable parent. Therefore, nullability in SDL is part of the error contract.

Clients should rely on stable error codes in extensions rather than comparing literal message text. For example, code VALIDATION_FAILED can accompany a safe list of field paths and constraint messages.

## 15. Testing validation with GraphQlTester

Test through actual GraphQL operations to verify SDL, argument binding, Bean Validation, and exception handling.

Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verifyNoInteractions;

@GraphQlTest(CustomerMutationController.class)
@Import(GraphQlValidationAdvice.class)
class CustomerValidationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockBean
    CustomerService customerService;

    @Test
    void rejectsInvalidEmailBeforeCallingService() {
        GraphQlTester.Response response = graphQlTester.document("""
                mutation {
                    registerCustomer(input: {
                        displayName: "Lan Nguyen"
                        email: "not-an-email"
                        age: 28
                        address: { city: "Da Nang" }
                    }) {
                        id
                        displayName
                    }
                }
                """)
                .execute();

        response.errors().satisfy(errors -> {
            assertThat(errors).isNotEmpty();
            assertThat(errors.get(0).getExtensions())
                    .containsEntry("code", "VALIDATION_FAILED");
        });

        verifyNoInteractions(customerService);
    }
}
~~~

The test requires a Validator bean in the application context. When using @GraphQlTest, if the test slice does not automatically load validation configuration, import a configuration containing LocalValidatorFactoryBean or the corresponding test configuration. Ensure a validation provider is present in the test runtime.

Cases that should be tested:

1. Valid input is processed by the resolver.
2. Missing or null non-null fields are rejected by GraphQL before Bean Validation.
3. Empty or whitespace-only strings are rejected by @NotBlank.
4. Values exceeding @Size, @Min, or @Max.
5. Nested objects undergo cascade validation.
6. Collections with invalid elements.
7. Cross-field constraints detect invalid date relationships.
8. Create and update validation groups execute the right group.
9. Omitted and explicit null preserve partial update semantics.
10. BindException is distinguished from ConstraintViolationException.
11. The service is not invoked when validation fails.
12. GraphQL errors have the right code/path and do not contain invalid values.

You can test validators individually with Jakarta Validator to verify constraints and class-level rules. However, validator unit tests do not replace tests through GraphQL because they do not check SDL, argument binding, or exception mapping.

## 16. Common errors and fixes

| Symptom | Cause | How to fix |
| --- | --- | --- |
| @Valid has no effect | Missing Validator bean or validation provider | Add the validation starter and check the application context |
| Outer object is validated but child object is not | Missing @Valid on the nested property | Add cascade validation on the right property |
| Empty string passes @Email | @Email does not replace a presence check | Combine @NotBlank with @Email |
| List with too many elements passes | No limit on collection | Use @Size(max = ...) on the list |
| Items in list are not validated | Missing container element constraint or @Valid | Use List<@NotBlank String> or List<@Valid ItemInput> |
| Client receives generic error | ConstraintViolationException is not mapped | Use @GraphQlExceptionHandler or DataFetcherExceptionResolver |
| BindException confused with validation | Binding errors and constraint errors are two different stages | Classify exceptions and return distinct error codes |
| Validation group does not run | Constraint does not belong to the selected group | Check groups on each constraint and @Validated |
| Constraint validator calls database causing slowness | Mixing structural validation with business rules | Move data-dependent checks into the service/domain |
| Response leaks sensitive data | Returning invalid value or raw exception message | Only return field paths, safe messages, and error codes |

## 17. Workflow for implementing validation on @Argument

When adding validation for a GraphQL input:

1. Declare structure, scalars, and nullability in SDL.
2. Create a Java input DTO/record with appropriate constraints.
3. Add a Bean Validation provider compatible with Spring Boot.
4. Ensure the application context has a Validator bean.
5. Use @Valid on the @Argument parameter to trigger object validation.
6. Use @Valid on nested properties and container element constraints for collections.
7. Use @Validated when validation groups or method validation are needed.
8. Distinguish ConstraintViolationException from BindException and GraphQL request errors.
9. Map errors into GraphQL errors with stable codes and without leaking invalid values.
10. Let the service/domain handle rules depending on data state and authorization.
11. Test valid inputs, invalid inputs, nested validation, groups, and verify the service is not called when validation fails.

## 18. Key points to remember

- GraphQL SDL checks input structure and types before Bean Validation runs.
- @Argument binds arguments into Java parameters; @Valid triggers cascade validation for input objects.
- A Bean Validation provider, such as spring-boot-starter-validation, is required.
- Use @NotBlank, @Size, @Min, @Max, and @Email according to data semantics.
- Mark @Valid on nested objects and object elements in collections for recursive checking.
- @Validated supports validation groups and method validation under the corresponding Spring mechanism.
- Use wrapper types for input fields that can be null or omitted.
- ConstraintViolationException indicates unsatisfied constraints; BindException indicates failure to bind arguments to the Java target.
- ArgumentValue<T> helps distinguish omitted and explicit null during partial updates.
- Bean Validation fits data-level rules; state-dependent business validation must live in the service/domain.
- Use GraphQlTester to test schema, binding, validation, and response errors.

Validation on @Argument creates a clear boundary between GraphQL data and application logic. When combining SDL, DTOs, Bean Validation, and business validation in their proper roles, Spring for GraphQL can reject bad inputs early, return consistent errors, and keep resolvers focused on business logic.

## References

- Spring for GraphQL — Annotated Controllers: https://docs.spring.io/spring-graphql/reference/controllers.html
- Spring for GraphQL — Exceptions: https://docs.spring.io/spring-graphql/reference/controllers.html#controllers-exceptions
- Jakarta Bean Validation Specification: https://jakarta.ee/specifications/bean-validation/3.0/
- Hibernate Validator Reference Guide: https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/
