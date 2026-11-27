# Validation on Input Objects

GraphQL APIs commonly receive data from clients through input objects, especially in Mutations that create or update resources. An SDL schema can require fields to be present and non-null, but many data rules need deeper checks: strings must not be empty, emails must be well-formed, element counts must stay within limits, nested objects must be valid, or multiple fields must satisfy a combined condition.

Spring for GraphQL supports Bean Validation on annotated controller methods. When the application has a Bean Validation `Validator`, `AnnotatedControllerConfigurer` can detect that validator. Controllers mark input parameters with `@Valid` or `@Validated`; Spring validates the object before invoking the method. If there is a constraint violation, execution raises `ConstraintViolationException`, and the application can then convert the error into GraphQL errors using exception resolution.

This lesson presents how to combine GraphQL input types with Jakarta Bean Validation, how to validate records/DTOs and nested objects, how to use validation groups, how to distinguish schema, binding, and validation errors, how to handle `ConstraintViolationException`, along with testing and principles for placing validation in the right layer.

## 1. Layers of input data validation

When a client sends an input object, the data goes through several steps before reaching the service:

1. GraphQL parses and validates the document.
2. GraphQL coercion checks scalar types, enums, lists, required fields, and nullability against the SDL.
3. Spring for GraphQL binds argument values into Java DTOs.
4. Bean Validation checks constraints on DTOs if requested by the controller method.
5. The controller calls the service/domain to check business rules and execute the use case.

Each step solves a different group of problems:

| Layer | Checks | Error example |
| --- | --- | --- |
| GraphQL SDL and coercion | Data types, required fields, nullability | `title: String!` is missing or receives null |
| Argument binding | Mapping GraphQL input to Java object | Unable to convert value to Java type |
| Bean Validation | Constraints on DTOs and nested objects | Blank title, malformed email |
| Service/domain | Rules depending on system state and data | ISBN already exists, author does not belong to tenant |

Do not use Bean Validation to replace SDL. For example, `String!` expresses the GraphQL contract that a field must not be null; `@NotBlank` expresses the additional rule that the string must contain at least one non-whitespace character.

## 2. Declaring input objects in GraphQL SDL

Suppose the API creates a book along with author information:

```graphql
input AuthorInput {
  name: String!
  email: String!
}

input CreateBookInput {
  title: String!
  isbn: String!
  publishedYear: Int
  author: AuthorInput!
  tags: [String!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
```

SDL guarantees:

- `input` is an input type, not an output object type.
- The mutation's `input` is required.
- `title`, `isbn`, `author`, and `tags` cannot be null.
- Each element in `tags` cannot be null.
- `publishedYear` can be null or omitted.

However, SDL does not state that title must contain characters, email must be validly formatted, ISBN must follow a specific pattern, or tags may contain at most 10 elements. Those constraints fit Bean Validation.

## 3. Declaring constraints on Java input DTOs

With Spring Boot 3 and above, use Jakarta Bean Validation (`jakarta.validation.*`). DTOs can be Java records:

```java
public record CreateBookInput(
        @NotBlank
        @Size(max = 200)
        String title,

        @NotBlank
        @Pattern(regexp = "^[0-9]{13}$")
        String isbn,

        @Min(1450)
        @Max(2100)
        Integer publishedYear,

        @NotNull
        @Valid
        AuthorInput author,

        @NotNull
        @Size(max = 10)
        List<@NotBlank String> tags) {
}
```

Nested input:

```java
public record AuthorInput(
        @NotBlank
        @Size(max = 100)
        String name,

        @NotBlank
        @Email
        String email) {
}
```

Commonly used annotations:

| Constraint | Meaning |
| --- | --- |
| `@NotNull` | Value must not be null |
| `@NotBlank` | String is non-null, non-empty, and has a non-whitespace character |
| `@NotEmpty` | String, collection, map, or array is non-null and non-empty |
| `@Size(min, max)` | Limits length or element count |
| `@Min`, `@Max` | Limits integer values |
| `@DecimalMin`, `@DecimalMax` | Limits decimal values |
| `@Positive`, `@PositiveOrZero` | Positive or non-negative value |
| `@Email` | Basic email format check |
| `@Pattern` | Validates a string against a regular expression |
| `@Past`, `@Future` | Checks a point in time in the past or future |

`@NotBlank` fits title and name. `@Email` does not automatically replace `@NotBlank`: an empty string may be considered not to violate the email constraint on its own, so combine both when email is required.

## 4. Enabling Bean Validation on controller arguments

The controller marks the input argument with `@Valid`:

```java
@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(
            @Argument("input") @Valid CreateBookInput input) {
        return bookService.create(input);
    }
}
```

When a Bean Validation `Validator` bean exists in the Spring ApplicationContext, `AnnotatedControllerConfigurer` auto-detects it and enables validation for annotated controller methods. Typically, Spring Boot applications use `spring-boot-starter-validation` to bring a Bean Validation provider and validator configuration into the context.

For Spring configurations not using Boot auto-configuration, you can declare `LocalValidatorFactoryBean`:

```java
@Configuration
public class ValidationConfiguration {

    @Bean
    public LocalValidatorFactoryBean validator() {
        return new LocalValidatorFactoryBean();
    }
}
```

Ensure dependencies and annotation namespaces are compatible with the platform version. Spring Boot 3+ uses `jakarta.validation`; older Spring Boot 2 applications use `javax.validation`.

Validation is executed before the controller method is called. If the input is invalid, code inside `bookService.create(input)` does not run.

## 5. Validation for nested input objects

An input object can contain another input object. For Bean Validation to descend into the nested object, the parent component or property must be marked with `@Valid`:

```java
public record CreateBookInput(
        @NotBlank
        String title,

        @NotNull
        @Valid
        AuthorInput author) {
}

public record AuthorInput(
        @NotBlank
        String name,

        @NotBlank
        @Email
        String email) {
}
```

`@Valid` triggers cascading validation: when checking `CreateBookInput`, the validator continues checking the constraints inside `AuthorInput`. If `@Valid` is missing on the `author` component, `AuthorInput`'s constraints will not be evaluated automatically just because the object was bound.

Distinguish two constraints:

- `@NotNull` requires the author object to have a value.
- `@Valid` requests checking the constraints inside the author object.

In the example, SDL already declared `author: AuthorInput!`, so GraphQL also blocks null before the controller. `@NotNull` is still useful if the DTO is reused in another flow not going through GraphQL or if you want to keep the validation contract at the Java layer.

## 6. Validation for lists and list elements

Input objects often contain lists of elements:

```graphql
input CreateOrderInput {
  note: String
  lines: [CreateOrderLineInput!]!
}

input CreateOrderLineInput {
  productId: ID!
  quantity: Int!
}
```

The DTO can declare constraints on the collection and cascade down to each element:

```java
public record CreateOrderInput(
        @Size(max = 500)
        String note,

        @NotEmpty
        @Size(max = 50)
        List<@Valid CreateOrderLineInput> lines) {
}

public record CreateOrderLineInput(
        @NotBlank
        String productId,

        @Positive
        int quantity) {
}
```

The constraints have different scopes:

- `@NotEmpty` requires the list to have at least one element.
- `@Size(max = 50)` limits the total number of elements.
- `List<@Valid CreateOrderLineInput>` requests cascade validation for each line.
- `@Positive` checks the quantity of each line.

If you need to constrain values directly on each scalar element, use type-use constraints:

```java
public record CreateBookInput(
        @NotEmpty
        @Size(max = 10)
        List<@NotBlank @Size(max = 30) String> tags) {
}
```

GraphQL SDL should still accurately describe the nullability of the list and elements. Bean Validation adds rules about count, length, or value that SDL does not express.

## 7. Validation for multi-field rules

Constraints like `@NotBlank` or `@Min` check individual properties. Some rules need to combine multiple fields, for example:

- End date must be after start date.
- Only one of email or phone may be provided.
- A range must have minimum less than maximum.

You can use a class-level constraint with a custom validator:

```java
@ValidDateRange
public record SearchPeriodInput(
        @NotNull LocalDate from,
        @NotNull LocalDate to) {
}
```

Annotation:

```java
@Constraint(validatedBy = DateRangeValidator.class)
@Target({ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
public @interface ValidDateRange {

    String message() default "End date must be after start date";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

Validator:

```java
public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, SearchPeriodInput> {

    @Override
    public boolean isValid(
            SearchPeriodInput value,
            ConstraintValidatorContext context) {

        if (value == null || value.from() == null || value.to() == null) {
            return true;
        }
        return value.to().isAfter(value.from());
    }
}
```

In the example, `@NotNull` is responsible for reporting an error if a date is missing; the class-level validator only checks the relationship between the two dates when both have values. Avoid creating duplicate errors for the same situation.

If you want to attach a class-level violation to a specific property, you can use `ConstraintValidatorContext` to disable the default violation and add a property node. This helps error metadata clearly indicate the related field.

## 8. Validation groups with @Validated

One DTO can be used across multiple use cases. Rules when creating may differ from rules when updating:

- When creating, ISBN is required.
- When updating, ISBN may be omitted.
- Certain constraints apply only to the publish operation.

Bean Validation supports validation groups:

```java
public interface Create {}
public interface Update {}
```

DTO:

```java
public record BookInput(
        @NotBlank(groups = Create.class)
        String title,

        @NotBlank(groups = Create.class)
        @Pattern(
                regexp = "^[0-9]{13}$",
                groups = {Create.class, Update.class})
        String isbn) {
}
```

Controller:

```java
@MutationMapping
public Book createBook(
        @Argument("input") @Validated(Create.class) BookInput input) {
    return bookService.create(input);
}

@MutationMapping
public Book updateBook(
        @Argument("input") @Validated(Update.class) BookInput input) {
    return bookService.update(input);
}
```

Spring's `@Validated` allows specifying the group to run. If groups are not used, `@Valid` is usually a concise way to run the default group.

When there are nested objects and custom groups, check how groups cascade. You can use `@ConvertGroup` if the child object needs to map the parent's group to a different group. Do not declare too many groups if rules only differ by a few business conditions; in that case, two separate input DTOs can be easier to understand.

## 9. Distinguishing GraphQL coercion, binding, and Bean Validation

Three input errors are commonly confused:

### GraphQL coercion error

SDL declares:

```graphql
input CreateBookInput {
  title: String!
  publishedYear: Int
}
```

If a client sends `publishedYear: "twenty"` or omits `title`, the GraphQL engine rejects the input due to a wrong type or missing non-null value. The controller method has not been called; Bean Validation has not run.

### Argument binding error

After GraphQL has coerced values, Spring binds the input map into the Java DTO. If conversion or object instantiation fails, `GraphQlArgumentBinder` can raise `BindException` containing field errors and the argument path.

For example, the Java DTO requires a type incompatible with the value already coerced by GraphQL. This is a data mapping error, not a constraint violation.

### Bean Validation error

The input has been bound successfully into a Java object, but violates a constraint such as `@NotBlank`, `@Email`, or `@Size`. In that case, Spring raises `ConstraintViolationException`.

| Error | Is controller method called? | Example |
| --- | --- | --- |
| GraphQL parse/validation/coercion | No | Missing `String!`, wrong scalar |
| Argument binding | No | Cannot bind input to constructor/property |
| Bean Validation | No | `title` is a whitespace-only string |
| Service/domain validation | Yes | ISBN already exists in database |

Spring for GraphQL does not support a `BindingResult` parameter the way Spring MVC commonly uses it for controllers to read validation errors directly. Validation errors are handled as exceptions via exception resolution.

## 10. Converting ConstraintViolationException to GraphQL errors

When Bean Validation fails, the exception contains a set of `ConstraintViolation` objects. You can map each violation to a GraphQL error so the client knows which property is invalid.

Example resolver:

```java
@Component
public class InputValidationExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected List<GraphQLError> resolveToMultipleErrors(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (!(exception instanceof ConstraintViolationException violationException)) {
            return null;
        }

        return violationException.getConstraintViolations().stream()
                .map(violation -> GraphqlErrorBuilder.newError(environment)
                        .errorType(ErrorType.BAD_REQUEST)
                        .message(violation.getMessage())
                        .extensions(Map.of(
                                "code", "INPUT_VALIDATION_FAILED",
                                "property", violation.getPropertyPath().toString()))
                        .build())
                .toList();
    }
}
```

What the resolver does:

1. Accepts only `ConstraintViolationException`; other exceptions are left for subsequent resolvers to handle.
2. Iterates over each constraint violation.
3. Uses `BAD_REQUEST` to classify the input error.
4. Puts the DTO's property path into extensions.
5. Uses `GraphqlErrorBuilder.newError(environment)` so the GraphQL error is attached to the exact executing field.

Example response:

```json
{
  "data": null,
  "errors": [
    {
      "message": "must not be blank",
      "path": ["createBook"],
      "extensions": {
        "classification": "BAD_REQUEST",
        "code": "INPUT_VALIDATION_FAILED",
        "property": "title"
      }
    },
    {
      "message": "must be a well-formed email address",
      "path": ["createBook"],
      "extensions": {
        "classification": "BAD_REQUEST",
        "code": "INPUT_VALIDATION_FAILED",
        "property": "author.email"
      }
    }
  ]
}
```

`path` in the GraphQL error points to the executing GraphQL field, in this example the `createBook` mutation. `property` in extensions is the property path inside the Java input object. The two kinds of paths serve two different purposes.

Do not include `violation.getInvalidValue()` in responses by default. Invalid values may contain emails, phone numbers, tokens, or personal data. The validation message and property path are usually sufficient for the client to highlight the field to fix.

## 11. Using @GraphQlExceptionHandler instead of a global resolver

If the exception only originates from annotated controller methods, you can handle it with `@GraphQlExceptionHandler`:

```java
@ControllerAdvice
public class GraphQlValidationAdvice {

    @GraphQlExceptionHandler
    public List<GraphQLError> handle(
            ConstraintViolationException exception,
            DataFetchingEnvironment environment) {

        return exception.getConstraintViolations().stream()
                .map(violation -> GraphqlErrorBuilder.newError(environment)
                        .errorType(ErrorType.BAD_REQUEST)
                        .message(violation.getMessage())
                        .extensions(Map.of(
                                "code", "INPUT_VALIDATION_FAILED",
                                "property", violation.getPropertyPath().toString()))
                        .build())
                .toList();
    }
}
```

Two options:

| Mechanism | When appropriate |
| --- | --- |
| `@GraphQlExceptionHandler` | Handling exceptions from annotated controllers, can be placed inside a controller or `@ControllerAdvice` |
| `DataFetcherExceptionResolver` | Shared policy for DataFetchers, including manually registered DataFetchers |

Choose one clear ownership mechanism for `ConstraintViolationException`. If the same exception is handled by both mechanisms, results can be unpredictable or create duplicate configuration.

## 12. Customizing validation messages

Clients should not depend on provider default messages like `must not be blank`. You can define messages directly on the constraint:

```java
public record CreateBookInput(
        @NotBlank(message = "Book title is required")
        @Size(max = 200, message = "Book title must not exceed 200 characters")
        String title) {
}
```

Or use message keys:

```java
public record CreateBookInput(
        @NotBlank(message = "{book.title.required}")
        @Size(max = 200, message = "{book.title.size}")
        String title) {
}
```

Message keys can be resolved via Bean Validation message bundles, e.g. `ValidationMessages.properties`:

```properties
book.title.required=Book title is required
book.title.size=Book title must not exceed 200 characters
```

If the API needs multiple languages, configure locale-specific message bundles and ensure the locale is passed into GraphQL execution appropriately. Clients should still use error codes for logic handling rather than parsing translated message strings.

## 13. Validation does not replace business rules

Bean Validation fits structural and data constraints:

- Required strings, lengths, patterns.
- Quantities, value ranges.
- Emails, URLs, or date formats.
- Nested inputs and list elements.
- Combined conditions across fields in the same DTO.

The following rules typically belong to the service/domain:

- ISBN or email already exists in the database.
- Author exists and belongs to the current tenant.
- User has permission to create or update the resource.
- Current state allows transitioning to the new state.
- Inventory quantity is sufficient at the time of the transaction.

Do not call the database from a constraint validator just to check uniqueness. Two concurrent requests can still pass validation before both write data. Uniqueness constraints must be enforced at the database level and conflicts handled in the service/domain.

A validator should be easy to test, have minimal side effects, and focus on data rules evaluable from the input. The service/domain must still check conditions depending on system state right at the time the use case executes.

## 14. Minimal dependencies and configuration

With Spring Boot, add the Bean Validation starter to the application:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
```

Or Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

The Boot starter provides the Bean Validation provider and necessary validator configuration. If configuring the Spring context manually, ensure there is a Bean Validation `Validator` bean, usually `LocalValidatorFactoryBean`, so `AnnotatedControllerConfigurer` can detect it.

Check namespace imports:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import org.springframework.validation.annotation.Validated;
```

Older Spring Boot 2 applications use the `javax.validation` package; do not mix annotations from both namespaces in the same application.

## 15. Testing input validation with GraphQlTester

Tests should send real GraphQL operations to confirm validation runs before the controller calls the service:

```java
@GraphQlTest(BookMutationController.class)
@Import(InputValidationExceptionResolver.class)
class BookInputValidationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockBean
    BookService bookService;

    @Test
    void rejectsBlankTitleBeforeCallingService() {
        graphQlTester.document("""
                mutation {
                    createBook(input: {
                        title: "   "
                        isbn: "9781234567890"
                        author: {
                            name: "An Nguyen"
                            email: "an@example.com"
                        }
                        tags: ["graphql"]
                    }) {
                        id
                    }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> {
                    assertThat(errors).hasSize(1);
                    assertThat(errors.get(0).getExtensions())
                            .containsEntry("code", "INPUT_VALIDATION_FAILED")
                            .containsEntry("property", "title");
                });

        verifyNoInteractions(bookService);
    }
}
```

The test assumes:

- The schema has mutation `createBook(input: CreateBookInput!)`.
- `BookMutationController` accepts `@Argument @Valid CreateBookInput`.
- `InputValidationExceptionResolver` is imported into the GraphQL test slice.
- The Bean Validation starter is present in the test runtime.

To test nested validation, send a malformed email and assert the property path is `author.email`. To test list element validation, send an empty tag and assert the path contains the element index according to the Bean Validation provider.

### Testing valid input

Besides rejection cases, include tests for valid input:

```java
@Test
void acceptsValidInput() {
    CreateBookInput input = new CreateBookInput(
            "Spring for GraphQL",
            "9781234567890",
            2026,
            new AuthorInput("An Nguyen", "an@example.com"),
            List.of("graphql"));

    given(bookService.create(input))
            .willReturn(new Book("book-1", "Spring for GraphQL"));

    graphQlTester.document("""
            mutation {
                createBook(input: {
                    title: "Spring for GraphQL"
                    isbn: "9781234567890"
                    publishedYear: 2026
                    author: {
                        name: "An Nguyen"
                        email: "an@example.com"
                    }
                    tags: ["graphql"]
                }) {
                    id
                    title
                }
            }
            """)
            .execute()
            .path("createBook.id")
            .entity(String.class)
            .isEqualTo("book-1");

    then(bookService).should().create(input);
}
```

The example assumes `Book` has a constructor and the fields selected in the response. Add imports along with models according to the actual application.

## 16. Common errors

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Constraints do not run | Missing Validator bean or missing Bean Validation provider | Add the starter and check the validator in the context |
| `@Valid` does not check nested objects | Nested property lacks `@Valid` | Add cascading validation on the component/property |
| Null nested object is not flagged | Only `@Valid` is present, no `@NotNull` | Use `@NotNull` when the object is required |
| Empty list is still valid | Only `@Size(max = ...)` is used | Add `@NotEmpty` or `@Size(min = 1)` |
| An element inside the list is not checked | Missing type-use `@Valid` or element constraint | Declare `List<@Valid ItemInput>` |
| `@Email` accepts an empty string | `@Email` is not equivalent to required | Combine with `@NotBlank` if required |
| Wrong type but ConstraintViolationResolver does not run | GraphQL coercion or argument binding failed before validation | Handle the appropriate request/binding error type |
| Service still runs despite invalid input | Controller parameter not marked `@Valid`/`@Validated` or Validator not detected | Check method signature and configuration |
| Cannot use `BindingResult` | Spring for GraphQL handles validation errors via exceptions | Use `@GraphQlExceptionHandler` or a resolver |
| Constraint group does not run | Controller selects a different group from the one declared on the constraint | Check `@Validated` and group membership |
| Error message leaks data | Returning invalid value or exception details | Only return the necessary message and property metadata |

## 17. Principles for designing input validation

- Use SDL to describe input types, scalars, required fields, and nullability.
- Use dedicated DTOs per input object or use case.
- Use `@Valid` on controller arguments to enable Bean Validation.
- Use `@Valid` on nested properties or list elements to cascade.
- Use `@NotNull`, `@NotBlank`, `@Size`, `@Pattern`, and constraints matching data semantics.
- Use `@Validated` when validation groups are needed.
- Keep Bean Validation focused on constraints evaluable from input.
- Let the service/domain check uniqueness, authorization, and system state.
- Distinguish GraphQL coercion errors, argument binding errors, and constraint violations.
- Normalize `ConstraintViolationException` into a stable GraphQL error code.
- Include the property path in extensions if clients need to highlight fields.
- Do not return invalid values, stack traces, or internal details to clients.
- Test valid inputs, invalid inputs, nested objects, and collection elements.

## 18. Hands-on exercise

Build an order creation mutation with nested input:

1. Declare `CreateOrderInput` and `CreateOrderLineInput` in SDL.
2. Create Java records for the two input DTOs.
3. Add constraints for product code, quantity, note, and line count.
4. Use `List<@Valid CreateOrderLineInput>` to validate each line.
5. Write a `@MutationMapping` accepting `@Argument @Valid CreateOrderInput`.
6. Configure a Bean Validation provider and verify the controller is called when input is valid.
7. Try sending an empty list, quantity of 0, blank product ID, and an overly long note.
8. Create a custom class-level constraint checking that the delivery date is after the order date.
9. Add validation groups for create and update.
10. Convert `ConstraintViolationException` into GraphQL errors with code `INPUT_VALIDATION_FAILED` and property path.
11. Test GraphQL coercion errors separately from Bean Validation errors.
12. Verify the service is not invoked when input violates constraints.

After the exercise, you should be able to explain at which stage validation occurs, how cascading works through nested inputs, when to use `@Valid` or `@Validated`, and why database-dependent rules must be checked in the service/domain.

## 19. References

- [Spring for GraphQL — Annotated Controllers: Validation](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/)

Exception details, validator auto-detection, and the `javax.validation`/`jakarta.validation` namespace depend on the Spring Framework and Spring Boot versions. When upgrading dependencies, check the reference documentation matching the version your application uses.
