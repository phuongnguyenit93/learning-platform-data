# @Valid

## Objectives

After this lesson, you will be able to:

- Explain the role of `@Valid` when receiving GraphQL inputs in Spring for GraphQL.
- Configure Bean Validation so Spring checks arguments before invoking a controller method.
- Place constraints on Java DTOs or records that receive data from GraphQL.
- Enable recursive validation for nested input objects and collection elements.
- Distinguish SDL constraints from Bean Validation and business rules.
- Use `@Validated` when validation groups are needed.
- Handle `ConstraintViolationException` using `@GraphQlExceptionHandler`.
- Test valid inputs, invalid inputs, and ensure the service does not run when validation fails.

## 1. What problem does @Valid solve?

GraphQL SDL can check the data types and nullability of inputs. For example, `String!` requires the client to provide a non-null string. However, SDL cannot fully express rules such as:

- A string must not be empty or whitespace-only.
- An email must have a valid format.
- A quantity must be greater than 0.
- A list must contain at least one element.
- An ISBN code must not exceed a specified length.
- Start and end dates must satisfy a business relationship.

Spring for GraphQL integrates Jakarta Bean Validation to check Java objects after GraphQL binds arguments to the controller method. When a parameter is marked with `@Valid`, Spring asks the Validator to check constraints on the object before invoking the method.

For example, a mutation receiving BookInput:

~~~graphql
input BookInput {
  title: String!
  isbn: String!
}

type Mutation {
  addBook(input: BookInput!): Book!
}
~~~

SDL guarantees both fields have String values and are non-null. However, an empty string is still a valid String according to GraphQL. The `@NotBlank` constraint can reject that case.

`@Valid` is the bridge between the GraphQL-bound input and the constraints declared in the Java DTO.

## 2. Configuring Bean Validation in Spring Boot

Spring for GraphQL only enables validation for annotated controllers when a `jakarta.validation.Validator` bean exists in the Spring application context. In Spring Boot, the standard way is to add the validation starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Use Spring Boot's dependency management to manage compatible versions; typically there is no need to specify a version for the starter manually.

The starter provides the Jakarta Bean Validation API and a validation provider such as Hibernate Validator. Spring Boot auto-configures the Validator, typically through `LocalValidatorFactoryBean`, so Spring for GraphQL can detect and use it.

If not using Spring Boot auto-configuration, you need to register the Validator bean manually, for example:

~~~java
@Configuration
public class ValidationConfiguration {

    @Bean
    LocalValidatorFactoryBean validator() {
        return new LocalValidatorFactoryBean();
    }
}
~~~

When `AnnotatedControllerConfigurer` finds a Validator bean, it enables Bean Validation support for method parameters marked with `@Valid` or `@Validated`.

If you only add the `@Valid` annotation without a validation provider or Validator bean, do not assume constraints will automatically be enforced.

## 3. Placing constraints on input DTOs

Suppose an API creates a book with a title and ISBN:

~~~graphql
input BookInput {
  title: String!
  isbn: String!
}

type Mutation {
  addBook(input: BookInput!): Book!
}
~~~

Java record:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record BookInput(
        @NotBlank
        String title,

        @NotBlank
        @Size(max = 13)
        String isbn) {
}
~~~

The constraints mean:

- `@NotBlank`: the value is non-null and must contain at least one non-whitespace character.
- `@Size(max = 13)`: the length does not exceed 13 characters.

With Java records, constraints can be placed on record components. The validation provider reads the record's metadata and checks the corresponding components.

Controller:

~~~java
@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book addBook(
            @Argument("input") @Valid BookInput input) {
        return bookService.addBook(input);
    }
}
~~~

Spring performs the following steps:

1. GraphQL checks the operation and coerces inputs according to the SDL.
2. Spring binds the `input` argument into `BookInput`.
3. Bean Validation checks the constraints triggered by `@Valid`.
4. If validation succeeds, Spring invokes `addBook`.
5. If validation fails, the method is not invoked and a `ConstraintViolationException` is raised to be handled in the exception chain.

Specifying `@Argument("input")` makes the argument name explicit and avoids relying on Java parameter name metadata. `@Valid` activates validation on the bound object.

## 4. How is @Valid different from constraint annotations?

The two groups of annotations serve different roles:

- `@Valid` requests validation of the object and cascades down to nested objects.
- Constraints such as `@NotBlank`, `@Positive`, `@Size`, and `@Email` define the conditions the data must satisfy.

Example:

~~~java
public record CustomerInput(
        @NotBlank String fullName,
        @Email String email) {
}
~~~

If you only declare the DTO as above without activating validation in the controller, the constraints may not be executed during argument processing.

~~~java
@MutationMapping
public Customer createCustomer(
        @Argument @Valid CustomerInput input) {
    return customerService.create(input);
}
~~~

Here, `@Valid` activates checking of the constraints on `CustomerInput`.

There is no need to place `@Valid` on each scalar field. Place constraints directly on fields or record components. `@Valid` on a property is meaningful when that property references an object requiring cascade validation.

## 5. Validation for nested input objects

An input object can contain another object. For validation to descend into the child object, the nested property must be marked with `@Valid`.

SDL:

~~~graphql
input AddressInput {
  street: String!
  city: String!
  postalCode: String
}

input CreateCustomerInput {
  fullName: String!
  email: String!
  address: AddressInput!
}

type Mutation {
  createCustomer(input: CreateCustomerInput!): Customer!
}
~~~

Java DTO:

~~~java
public record AddressInput(
        @NotBlank String street,
        @NotBlank String city,
        @Pattern(regexp = "\\d{5,6}")
        String postalCode) {
}

public record CreateCustomerInput(
        @NotBlank String fullName,
        @Email String email,
        @NotNull @Valid AddressInput address) {
}
~~~

Controller:

~~~java
@MutationMapping
public Customer createCustomer(
        @Argument("input") @Valid CreateCustomerInput input) {
    return customerService.create(input);
}
~~~

There are two levels of validation:

- `@Valid` on the controller parameter triggers validation of `CreateCustomerInput`.
- `@Valid` on the `address` property tells the validator to continue checking the constraints of `AddressInput`.

If `@Valid` is missing on the nested property, the validator may check the parent object's constraints without cascading down to the constraints inside the child object.

This is a common reason why a parent DTO is validated while data inside an address, payment details, or child object still goes unchecked.

## 6. Validation for Lists and elements in a List

For collections, distinguish constraints on the collection itself from constraints on each element.

SDL:

~~~graphql
input OrderLineInput {
  productId: ID!
  quantity: Int!
}

input CreateOrderInput {
  items: [OrderLineInput!]!
}

type Mutation {
  createOrder(input: CreateOrderInput!): Order!
}
~~~

Java:

~~~java
public record OrderLineInput(
        @NotBlank String productId,
        @Positive Integer quantity) {
}

public record CreateOrderInput(
        @NotEmpty
        List<@NotNull @Valid OrderLineInput> items) {
}
~~~

Meaning:

- `@NotEmpty` requires the list to have at least one element.
- `@NotNull` on the element prevents a null element.
- `@Valid` on the element triggers validation for each `OrderLineInput`.
- `@NotBlank` checks productId.
- `@Positive` requires quantity to be greater than 0.

With nested collections, you can combine container constraints and type-use constraints on elements. Declare concrete generic types, such as `List<OrderLineInput>`, so the binder creates the right Java objects.

A non-empty list does not mean every element is valid. You need to check the collection size, null elements, and each object's constraints.

## 7. SDL nullability and Bean Validation complement each other

GraphQL SDL and Bean Validation check data at two different layers.

| Rule | SDL | Bean Validation |
|---|---|---|
| Required, non-null field | `String!` | `@NotNull` |
| Non-empty/non-whitespace string | No equivalent standard constraint | `@NotBlank` |
| Non-empty string | No equivalent standard constraint | `@NotEmpty` |
| Length limit | No equivalent standard constraint | `@Size` |
| Number greater than 0 | Only checks numeric type | `@Positive` |
| Email format | Only checks String | `@Email` |
| Minimum number of elements | List type does not specify size | `@Size` or `@NotEmpty` |

For example, `title: String!` rejects null or being omitted when there is no default value, but still accepts `""` and `"   "`. `@NotBlank` adds the rule that it must not be empty or whitespace-only.

Similarly, `quantity: Int!` only ensures the input is a non-null integer. It still accepts 0 or negative numbers. `@Positive` is what expresses the greater-than-0 rule.

You can use both SDL and Bean Validation for the same property if you want an explicit contract and the DTO is also reused elsewhere. However, understand that some constraints like `@NotNull` may repeat what SDL has already guaranteed before the controller is called.

## 8. @Valid and @Validated: when to use each?

`@Valid` belongs to Jakarta Bean Validation and triggers validation for the default group (`Default`). `@Validated` belongs to Spring and allows specifying validation groups.

Example group declarations:

~~~java
public interface CreateChecks {
}

public interface UpdateChecks {
}
~~~

DTO:

~~~java
public record BookInput(
        @NotBlank(groups = {
                CreateChecks.class,
                UpdateChecks.class
        })
        String title,

        @NotBlank(groups = CreateChecks.class)
        String isbn) {
}
~~~

Controller using a group on creation:

~~~java
@MutationMapping
public Book addBook(
        @Argument("input")
        @Validated(CreateChecks.class) BookInput input) {
    return bookService.addBook(input);
}
~~~

An update method can use another group:

~~~java
@MutationMapping
public Book updateBook(
        @Argument String id,
        @Argument("input")
        @Validated(UpdateChecks.class) BookInput input) {
    return bookService.updateBook(id, input);
}
~~~

In this example:

- On creation, both title and isbn are checked.
- On update, title is checked; isbn is not in the UpdateChecks group, so that constraint does not run.

Constraints that do not declare a group belong to `Default.class` by default. If you only invoke validation with a custom group, constraints belonging to Default do not automatically run unless a group sequence or group configuration is designed to include them.

Use `@Valid` when only standard validation is needed. Use `@Validated(Group.class)` when the same DTO has different rules across creation, update, or business flows.

## 9. Multi-level validation and custom constraints

Built-in constraints cover many cases, but sometimes you need to check relationships between multiple fields. For example, the end date must be after the start date, or an input must have at least one of the email and phone fields.

You can create a class-level constraint with a custom annotation and a `ConstraintValidator`.

DTO:

~~~java
@ValidDateRange
public record BookingInput(
        @NotNull LocalDate startDate,
        @NotNull LocalDate endDate) {
}
~~~

Annotation:

~~~java
import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = DateRangeValidator.class)
public @interface ValidDateRange {

    String message() default "endDate must be after startDate";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, BookingInput> {

    @Override
    public boolean isValid(
            BookingInput value,
            ConstraintValidatorContext context) {

        if (value == null ||
                value.startDate() == null ||
                value.endDate() == null) {
            return true;
        }

        return value.endDate().isAfter(value.startDate());
    }
}
~~~

The `@NotNull` constraints handle missing dates. The class-level validator only checks the relationship between the two dates when both have values.

When you need to attach the error to a specific property rather than the object name, `ConstraintValidatorContext` allows building the appropriate property node. This helps the client display the error next to the corresponding field.

Do not cram all domain rules into custom validators. Validation is suited for conditions that can be checked from the input object. Rules that depend on the database, access permissions, or current state should remain in the service/domain layer.

## 10. Validation failure happens before the controller method runs

When Bean Validation detects a constraint violation, Spring for GraphQL does not proceed to invoke the handler method. A `ConstraintViolationException` is raised and enters the exception handling chain.

This means:

- The service is not called.
- No business transaction is started from that method.
- The controller does not receive a "nearly valid" object to decide on its own.
- The exception needs to be handled to produce an appropriate GraphQL error.

Unlike Spring MVC, annotated GraphQL controllers do not support accepting `BindingResult` in the method signature to read validation errors right next to the parameter. Errors are handled through the exception mechanism.

This is a key point to remember when migrating a REST controller to GraphQL: you cannot copy Spring MVC's `BindingResult` parameter pattern directly into a GraphQL handler method.

## 11. Handling ConstraintViolationException with @GraphQlExceptionHandler

Spring for GraphQL supports `@GraphQlExceptionHandler` to convert exceptions raised from controller invocations into GraphQL errors. You can place the handler inside a controller for local error handling or inside `@ControllerAdvice` to apply across multiple controllers.

Example global handler:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import jakarta.validation.ConstraintViolationException;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlValidationAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handle(
            ConstraintViolationException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        List<Map<String, String>> violations =
                exception.getConstraintViolations().stream()
                        .map(violation -> Map.of(
                                "field",
                                violation.getPropertyPath().toString(),
                                "message",
                                violation.getMessage()))
                        .toList();

        return errorBuilder
                .errorType(ErrorType.BAD_REQUEST)
                .message("Input validation failed")
                .extensions(Map.of(
                        "code", "INPUT_VALIDATION_FAILED",
                        "violations", violations))
                .build();
    }
}
~~~

Spring prepares `GraphqlErrorBuilder` according to the current DataFetchingEnvironment and provides it to the exception handler method. As a result, the error can carry the path and source location of the field being resolved.

Illustrative response example:

~~~json
{
  "data": {
    "addBook": null
  },
  "errors": [
    {
      "message": "Input validation failed",
      "path": ["addBook"],
      "extensions": {
        "classification": "BAD_REQUEST",
        "code": "INPUT_VALIDATION_FAILED",
        "violations": [
          {
            "field": "addBook.input.title",
            "message": "must not be blank"
          }
        ]
      }
    }
  ]
}
~~~

The violation path content depends on the object structure and the Bean Validation provider. Do not include the rejected input value in the response because it may contain personal data or sensitive information.

If you want a simpler message, you can return only a generic error code without exposing the list of constraints. What matters is keeping the error format stable for clients to handle.

## 12. Distinguishing GraphQL validation, binding errors, and Bean Validation

Checking steps occur at different moments:

| Check type | Example | Timing |
|---|---|---|
| GraphQL parse/validation | Syntax error in query, non-existent field | Before DataFetcher |
| GraphQL input coercion | Passing string to Int argument, missing non-null field | Before DataFetcher |
| Argument binding | Unable to instantiate DTO or property conversion failed | When Spring binds arguments |
| Bean Validation | Empty string, negative number, invalid email | After binding, before method invocation |
| Business validation | Product out of stock, user lacks permission | Inside service/domain |

Example:

- SDL declares `quantity: Int!`; passing `"two"` will be rejected by GraphQL before the controller.
- Passing `quantity: 0` is a valid Int type, but `@Positive` will reject it before the method runs.
- Passing `quantity: 2` is valid data, but the service can still reject it because the product is out of stock.

Failed argument binding can raise `BindException`; failed Bean Validation raises `ConstraintViolationException` via the annotated controller validation mechanism. The two error types should be handled separately if clients need different error codes or detail structures.

## 13. Do not replace business validation with @Valid

Bean Validation is suitable for checking the structure and conditions of input data. However, not every business rule can be checked on a DTO.

Example:

- `@Positive quantity` checks that the quantity is greater than 0.
- The service checks whether that quantity exceeds current inventory.
- `@Email` checks basic email format.
- The service checks whether the email has already been registered.
- `@NotNull customerId` checks that a customer ID is present.
- The service checks whether the current user has permission to place an order for that customer.

Checks that depend on the database, security principal, transactions, or domain state should live in the service/domain layer.

Do not call repositories from `ConstraintValidator` for every constraint just to group all validation in DTOs. That can create hidden queries, make transactions hard to control, and make validation difficult to test.

## 14. Testing @Valid with GraphQlTester

Test from actual GraphQL operations to verify that SDL, argument binding, Bean Validation, and exception handling work together.

Example input:

~~~java
public record BookInput(
        @NotBlank String title,
        @NotBlank @Size(max = 13) String isbn) {
}
~~~

Mutation:

~~~java
@MutationMapping
public Book addBook(
        @Argument("input") @Valid BookInput input) {
    return bookService.addBook(input);
}
~~~

Invalid data test:

~~~java
@Test
void shouldRejectBlankTitleBeforeCallingService() {
    graphQlTester.document("""
            mutation AddBook($input: BookInput!) {
                addBook(input: $input) {
                    id
                }
            }
            """)
            .variable("input", Map.of(
                    "title", "   ",
                    "isbn", "1234567890123"))
            .execute()
            .errors()
            .satisfy(errors -> {
                assertThat(errors).isNotEmpty();
                assertThat(errors.get(0).getMessage())
                        .isEqualTo("Input validation failed");
            });

    verifyNoInteractions(bookService);
}
~~~

This test assumes the application has registered `GraphQlValidationAdvice` as in the previous example. Verifying that the service is not invoked proves validation happens before method invocation.

Valid data test:

~~~java
@Test
void shouldCreateBookWhenInputIsValid() {
    when(bookService.addBook(any(BookInput.class)))
            .thenReturn(new Book(
                    "b-01", "GraphQL in Practice", "1234567890123"));

    graphQlTester.document("""
            mutation AddBook($input: BookInput!) {
                addBook(input: $input) {
                    title
                    isbn
                }
            }
            """)
            .variable("input", Map.of(
                    "title", "GraphQL in Practice",
                    "isbn", "1234567890123"))
            .execute()
            .path("addBook.title")
            .entity(String.class)
            .isEqualTo("GraphQL in Practice");

    verify(bookService).addBook(any(BookInput.class));
}
~~~

Cases that should be included in the test suite:

1. Valid input is bound and the method runs.
2. Empty or whitespace-only string is rejected by `@NotBlank`.
3. Over-length string is rejected by `@Size`.
4. Nested objects undergo cascade validation.
5. Invalid list elements are detected.
6. Constraint groups are applied properly for create/update operations.
7. GraphQL non-null or scalar coercion fails before Bean Validation runs.
8. `ConstraintViolationException` is converted into a GraphQL error with a stable code.
9. The service is not invoked when validation fails.
10. Responses do not leak sensitive input values.

## 15. Common errors

| Symptom | Possible cause | How to fix |
|---|---|---|
| `@Valid` does not run | Missing Validator bean or validation provider | Add the validation starter or register a Validator |
| Parent DTO is validated but child object is not | Missing `@Valid` on the nested property | Mark cascade validation |
| List does not check each element | Constraints only placed on the collection | Use `List<@Valid ItemInput>` |
| Empty string is still accepted | Only GraphQL `String!` or `@NotNull` is used | Use `@NotBlank` |
| Zero is still accepted | SDL `Int!` only checks type and null | Use `@Positive` or an appropriate constraint |
| Constraint group does not run | Controller selects a different group from the one on the constraint | Align `@Validated` and the groups attribute |
| Controller does not receive BindingResult | GraphQL annotated controller does not support this pattern like Spring MVC | Handle exceptions via `@GraphQlExceptionHandler` |
| Client receives overly detailed errors | Returning raw violation data or rejected values | Only expose necessary field paths, messages, and error codes |

## 16. @Valid implementation checklist

Before releasing a mutation or Query that accepts input:

- [ ] A Bean Validation provider and Validator bean exist.
- [ ] DTOs have constraints matching the data rules.
- [ ] Input parameters are marked with `@Valid` or `@Validated`.
- [ ] Nested objects have `@Valid` to cascade.
- [ ] Collections have constraints on both the container and elements when needed.
- [ ] SDL nullability matches the input contract.
- [ ] Validation groups are selected properly for each use case.
- [ ] `ConstraintViolationException` is converted into a stable GraphQL error.
- [ ] Business validation remains in the service/domain layer.
- [ ] Tests verify the method/service does not run when validation fails.
- [ ] Error responses do not leak sensitive input values.

## Conclusion

`@Valid` allows Spring for GraphQL to trigger Jakarta Bean Validation on arguments already bound into Java objects. When a Validator bean is present, `AnnotatedControllerConfigurer` checks parameters before invoking the controller method. Constraint violations raise `ConstraintViolationException`, which can be converted into GraphQL errors using `@GraphQlExceptionHandler` or an appropriate exception resolver mechanism.

SDL checks structure, types, and nullability; Bean Validation checks data conditions; the service/domain layer handles rules depending on state and business logic. Combining the three layers properly, cascading validation for nested objects, and testing with `GraphQlTester` make input APIs clearer, easier to use, and safer.

## References

- [Spring for GraphQL — Annotated Controllers, Validation](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.validation)
- [Spring for GraphQL — Exception Handling](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.exception-handler)
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/)
- [Jakarta Validation API — @Valid](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/valid)
