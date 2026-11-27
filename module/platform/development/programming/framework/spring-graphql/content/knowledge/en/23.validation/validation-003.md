# `@Validated` in Spring for GraphQL

GraphQL SDL checks data types, required arguments, and nullability before calling a resolver. However, rules such as a title cannot be blank, quantity must be greater than 0, or an ISBN may only have a certain length belong to the application's business validation.

Spring for GraphQL integrates Jakarta Bean Validation with annotated controllers. When a `Validator` bean exists in the Spring context, `AnnotatedControllerConfigurer` can validate handler parameters before invoking the method. You can use `@Valid` to trigger validation with the default group, or use Spring's `@Validated` to select validation groups such as create and update.

## 1. What is `@Validated`?

`@Validated` resides in the `org.springframework.validation.annotation` package. It is a Spring annotation that extends Bean Validation usage with the ability to specify validation groups.

```java
import org.springframework.validation.annotation.Validated;

@Validated
public class Example {
}
```

In Spring for GraphQL, the common usage is placing `@Validated` directly on a method parameter of an annotated controller:

```java
@MutationMapping
public Book createBook(
        @Argument("input") @Validated(OnCreate.class) BookInput input) {
    return bookService.create(input);
}
```

`OnCreate.class` is the validation group applied to `BookInput`. Thanks to this, the same DTO can be used across multiple mutations while each use case applies different rules.

## 2. Preparing a Bean Validation provider

For validation to work, the application needs a Bean Validation provider and a `Validator` bean that Spring for GraphQL can detect. With Spring Boot, the common dependency is `spring-boot-starter-validation`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

This starter brings an implementation such as Hibernate Validator onto the classpath, and Spring Boot usually auto-configures the required validator. If configuring the application manually or if no validator bean is created automatically, you can declare a `LocalValidatorFactoryBean`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class ValidationConfiguration {

    @Bean
    LocalValidatorFactoryBean validator() {
        return new LocalValidatorFactoryBean();
    }
}
```

`LocalValidatorFactoryBean` integrates Jakarta Bean Validation with Spring and can be injected as `jakarta.validation.Validator` or Spring's `org.springframework.validation.Validator`.

With Spring Boot 3 and above, use the `jakarta.validation.*` package. Older examples using `javax.validation.*` belong to the dependency generation prior to Jakarta EE 9; do not mix the two namespaces in the same application.

## 3. Declaring constraints on an input object

Suppose the API has a mutation to create a book:

```graphql
input BookInput {
    id: ID
    title: String!
    isbn: String
    description: String
}

type Mutation {
    createBook(input: BookInput!): Book!
    updateBook(input: BookInput!): Book!
}
```

A Java record can declare constraints on its components:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record BookInput(
        @NotBlank String title,
        @NotBlank @Size(max = 13) String isbn,
        @Size(max = 500) String description) {
}
```

Meaning of the constraints:

- `@NotBlank` requires the string to be non-null and contain at least one non-whitespace character.
- `@Size(max = 13)` limits the string length to at most 13 characters.
- `description` is nullable in SDL and can also be null in Java; if a value is present, it must not exceed 500 characters.

`String!` in SDL only guarantees that the client must provide a non-null value. It does not guarantee the string has content. `@NotBlank` adds that rule at the Bean Validation layer.

## 4. Enabling validation with `@Valid`

For an input object using the default group, place `@Valid` on the `@Argument` parameter:

```java
import jakarta.validation.Valid;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(@Argument("input") @Valid BookInput input) {
        return bookService.create(input);
    }
}
```

Spring for GraphQL binds the argument to `BookInput`, runs Bean Validation, and only then invokes the method. If the data violates a constraint, the `createBook` method is not executed and the validation exception is passed into GraphQL exception handling.

`@Valid` is a Jakarta Validation annotation used to request validation/cascading under the default group. `@Valid` itself is not a constraint and does not select a different validation group.

## 5. `@Validated` and validation groups

Validation groups allow using the same DTO while applying different rules per action. For example, creating a book requires an ISBN, whereas updating only requires an ID and title.

First, declare the groups:

```java
import jakarta.validation.groups.Default;

public interface OnCreate extends Default {
}

public interface OnUpdate extends Default {
}
```

Both groups extend `Default`, so when validating `OnCreate` or `OnUpdate`, constraints belonging to the default group are also applied.

DTO:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record BookInput(
        @NotBlank String title,
        @NotBlank(groups = OnCreate.class) String isbn,
        @NotNull(groups = OnUpdate.class) String id,
        @Size(max = 500) String description) {
}
```

Controller:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;
import org.springframework.validation.annotation.Validated;

@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(
            @Argument("input") @Validated(OnCreate.class) BookInput input) {
        return bookService.create(input);
    }

    @MutationMapping
    public Book updateBook(
            @Argument("input") @Validated(OnUpdate.class) BookInput input) {
        return bookService.update(input);
    }
}
```

With the declarations above:

- Both create and update require `title` not to be blank because the constraint belongs to the `Default` group, which is inherited by both groups.
- Create requires `isbn` not to be blank.
- Update requires `id` to be non-null.
- `description` must always remain within the length limit if provided.

If a group does not extend `Default`, constraints belonging to `Default` will not automatically run when validating only that group. Decide clearly on group inheritance or assign constraints to the necessary groups to avoid accidentally skipping validation.

## 6. Distinguishing `@Valid` and `@Validated`

| Characteristic | `@Valid` | `@Validated` |
| --- | --- | --- |
| Package | `jakarta.validation.Valid` | `org.springframework.validation.annotation.Validated` |
| Origin | Jakarta Bean Validation | Spring Framework |
| Purpose | Triggers cascade validation using the default group | Triggers validation in Spring integration and allows selecting groups |
| Group selection | Has no group attribute | Can pass one or more group classes |
| Usage in GraphQL | `@Argument @Valid Input input` | `@Argument @Validated(OnCreate.class) Input input` |

Choose `@Valid` when only default constraints need to be applied. Choose `@Validated` when a mutation needs specific groups, such as `OnCreate`, `OnUpdate`, or `AdminOperation`.

There is no need to place both `@Valid` and `@Validated` on the same parameter just to "turn on" validation. Choose the annotation matching the groups to run and declare `@Valid` on nested properties when cascading down to child objects is needed.

## 7. Cascade validation for nested objects and collections

`@Validated` selects the group on the controller parameter, while `@Valid` on a nested property instructs the validator to descend into the child object.

Schema example:

```graphql
input OrderLineInput {
    productId: ID!
    quantity: Int!
}

input PlaceOrderInput {
    customerId: ID!
    lines: [OrderLineInput!]!
}

type Mutation {
    placeOrder(input: PlaceOrderInput!): Order!
}
```

DTO:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Positive;
import java.util.List;

public record OrderLineInput(
        @NotBlank String productId,
        @Positive Integer quantity) {
}

public record PlaceOrderInput(
        @NotBlank String customerId,
        @NotEmpty List<@Valid OrderLineInput> lines) {
}
```

Controller:

```java
@MutationMapping
public Order placeOrder(
        @Argument("input") @Validated(OnCreate.class) PlaceOrderInput input) {
    return orderService.place(input);
}
```

`@NotEmpty` requires the list to have at least one element. `@Valid` on the collection element instructs the validator to check each `OrderLineInput`; `@Positive` ensures quantity is greater than 0. Without cascading, constraints inside child objects may not be executed when only the parent object is validated.

For nested objects with their own groups, the group cascades by default. You can use `@ConvertGroup` when you need to convert from the parent object's group to another group on the child object.

## 8. Validation directly on scalar arguments

Bean Validation in annotated controllers does not only apply to input objects. Other method parameters can also be validated directly with constraints.

Example query with keyword and page size:

```graphql
type Query {
    searchBooks(keyword: String!, pageSize: Int = 20): [Book!]!
}
```

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

@QueryMapping
public List<Book> searchBooks(
        @Argument("keyword") @NotBlank String keyword,
        @Argument("pageSize") @Min(1) @Max(100) Integer pageSize) {
    return bookService.search(keyword, pageSize);
}
```

Here `@NotBlank`, `@Min`, and `@Max` check scalar values after GraphQL has parsed and bound the arguments. `pageSize` has a default of 20 in SDL; Bean Validation restricts the value clients can pass to between 1 and 100.

## 9. SDL validation and Bean Validation solve two different layers

The GraphQL engine checks the schema contract before calling the resolver. Bean Validation checks rules on Java objects/parameters after arguments have been bound.

| Rule | Appropriate place |
| --- | --- |
| Argument must be present | SDL: `id: ID!` |
| Value must be an integer | GraphQL scalar `Int` |
| String must not be blank | Bean Validation: `@NotBlank` |
| Quantity must be greater than 0 | Bean Validation: `@Positive` |
| List must have elements | Bean Validation: `@NotEmpty` |
| Fields within input must satisfy cross-field relationships | Class-level constraint or appropriate validation logic |
| User has permission to act on the resource | Authorization/service/domain, not Bean Validation alone |
| ISBN must be unique in the database | Service/domain and database constraint |

Do not use Bean Validation to replace the GraphQL type system. For example, if `id` must be non-null, declare `ID!` in SDL; `@NotNull` can add a check in Java but does not change the schema contract.

## 10. Custom constraints and multi-field rules

Standard constraints like `@NotBlank`, `@Size`, and `@Positive` are suitable for single-value checks. For rules depending on multiple fields, you can create a class-level constraint.

Example of an input with start and end dates:

```java
@ValidDateRange
public record BookingInput(
        @NotNull LocalDate startDate,
        @NotNull LocalDate endDate) {
}
```

`@ValidDateRange` is an application-defined custom constraint, with `ConstraintValidator<ValidDateRange, BookingInput>` checking that `endDate` is not before `startDate`. When the constraint is invalid, the validator creates a violation attached to the object or appropriate property.

Custom validators should check deterministic rules from the input data. Avoid making network calls or database queries inside a validator to check permissions, existence, or uniqueness; those rules typically belong to the application service/domain and require transaction/concurrency handling.

## 11. Handling validation groups in API design

Validation groups are useful when the same input object serves multiple use cases, but avoid creating too many groups that make rules hard to understand.

One way to organize them:

- `Default`: rules that always apply to all operations, e.g., title not blank.
- `OnCreate`: rules that apply only when creating, e.g., required ISBN.
- `OnUpdate`: rules that apply only when updating, e.g., ID must be present.
- `OnPublish`: rules that must be satisfied when publishing, e.g., content and cover image are complete.

Name groups by use case rather than by screen or client name. A group should represent a stable, meaningful set of rules on the server.

If create and update have significantly different inputs, two separate input types are sometimes easier to understand and safer than one large DTO with many groups. Validation groups are a tool for reusing constraints, not a reason to force every mutation into a single input object.

## 12. Validation errors are converted to GraphQL errors

When validation fails, Spring for GraphQL raises `ConstraintViolationException`. The exception goes through the GraphQL error handling mechanism; the controller method is not called.

You can handle it with `@GraphQlExceptionHandler` in a controller or `@ControllerAdvice` to standardize errors for clients:

```java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import jakarta.validation.ConstraintViolationException;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlValidationAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleValidation(
            ConstraintViolationException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
                .errorType(ErrorType.BAD_REQUEST)
                .message("Invalid input data")
                .extensions(java.util.Map.of("code", "VALIDATION_FAILED"))
                .build();
    }
}
```

The example above returns a generic message and a stable error code. If you want to return a list of invalid fields, transform `ConstraintViolation` into a filtered `extensions` structure containing only the necessary field paths and error codes. Avoid putting invalid values, personal information, internal class names, or implementation details into the response.

Another option is handling exceptions via `DataFetcherExceptionResolver`. Choose one consistent mechanism so the same exception is not mapped differently across controllers.

## 13. Distinguishing binding errors and validation errors

These two types of errors often appear close together, but they happen at two different steps:

1. **Binding error:** Spring cannot convert a GraphQL argument to the target Java type, for example an input object is incompatible with the constructor/property or a value cannot be converted. Spring for GraphQL may raise `BindException`.
2. **Validation error:** Binding succeeds, but the object violates a constraint such as `@NotBlank`, `@Positive`, or an active group. Spring for GraphQL raises `ConstraintViolationException`.

For example, a client sending `quantity: "many"` for an `Int` argument can be rejected by GraphQL during parsing/coercion before the method is called. If the client sends `quantity: -2`, the value is a valid `Int` but violates `@Positive`; this is a Bean Validation error.

Classify these errors clearly so the client knows whether to fix data types, input structure, or business values.

## 14. `@Validated` on controller parameters vs. at the class level

In Spring for GraphQL annotated controllers, the direct way to select a validation group for an argument is to place `@Validated(Group.class)` directly on the handler method parameter.

Spring's `@Validated` is also used at the class or method level for Spring-driven method validation via AOP, typically with `MethodValidationPostProcessor`. This is Spring's general method validation mechanism, distinct from `AnnotatedControllerConfigurer` validating GraphQL controller arguments. Do not just add `@Validated` at the class level and assume every GraphQL input will undergo cascade validation under the desired group; place the annotation on the parameter to validate and test the actual handler.

If using AOP method validation for services, you can place `@Validated` on the service class and constraints on service method parameters. In that case, you need to understand proxies/AOP, self-invocation, and the service's exception path. Regardless of which layer it is used in, critical business rules should still be enforced in the application service/domain so they do not rely solely on the GraphQL adapter.

## 15. Testing `@Validated` with GraphQlTester

Tests should verify both valid and invalid cases, and confirm that the service is not called when validation fails.

Example book creation mutation with invalid input:

```java
import java.util.Map;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void createBookRejectsBlankTitle() {
    graphQlTester.document("""
            mutation CreateBook($input: BookInput!) {
                createBook(input: $input) {
                    id
                    title
                }
            }
            """)
        .variable("input", Map.of(
                "title", "   ",
                "isbn", "9781234567890"))
        .execute()
        .errors()
        .satisfy(errors -> assertThat(errors).isNotEmpty());

    verifyNoInteractions(bookService);
}
```

The test assumes `GraphQlTester`, `bookService`, and mocks/fixtures are configured in the test context. You can assert `extensions.code` if the exception handler standardizes error codes.

Testing validation groups with two independent requests:

```java
@Test
void createBookRequiresIsbn() {
    graphQlTester.document("""
            mutation {
                createBook(input: { title: "Spring GraphQL" }) {
                    id
                }
            }
            """)
        .execute()
        .errors()
        .satisfy(errors -> assertThat(errors).isNotEmpty());

    verifyNoInteractions(bookService);
}

@Test
void updateBookDoesNotRequireIsbn() {
    graphQlTester.document("""
            mutation {
                updateBook(input: { id: "book-10", title: "Updated title" }) {
                    id
                    title
                }
            }
            """)
        .execute()
        .errors()
        .verify();
}
```

The test assumes `graphQlTester` and `bookService` are configured in the test context; for the successful update test, the mock service needs to return a valid `Book`. The create request missing ISBN is blocked by `OnCreate`, while the update request does not require ISBN because `isbn` does not belong to `OnUpdate`. Both still apply `Default` constraints because the groups extend `Default`.

Cases that should be tested:

1. Default group constraints apply to both create and update.
2. `OnCreate` constraints apply only to the create mutation.
3. `OnUpdate` constraints apply only to the update mutation.
4. Nested objects and collections undergo cascade validation via `@Valid`.
5. Scalar arguments violating `@NotBlank`, `@Min`, or `@Max` are rejected.
6. Binding errors are distinguished from constraint violations.
7. Handler services are not invoked when validation fails.
8. GraphQL errors do not leak invalid values or internal information.

## 16. Common errors

| Symptom | Cause | How to fix |
| --- | --- | --- |
| `@Valid` does not run | Missing Validator bean/provider or annotation not placed on parameter | Add the validation starter/Validator bean and place `@Valid` or `@Validated`. |
| Group `OnCreate` does not run | Mistakenly used `@Valid` or did not pass the group into `@Validated` | Use `@Validated(OnCreate.class)` on the parameter. |
| Default constraints do not run when selecting a group | Custom group does not extend Default and constraints do not declare that group | Extend `Default` or assign constraints to the necessary group. |
| Fields in child object are not checked | Missing `@Valid` on the property or collection element | Add cascade validation in the right place. |
| `String!` still accepts empty strings | Non-Null only rejects null, does not check content | Use `@NotBlank` or an appropriate constraint. |
| Method is called even though input is invalid | Validation is not enabled or validator is not detected | Check the validator bean, annotations, and integration tests. |
| Client sees binding error instead of validation | Argument could not be bound before Bean Validation ran | Check SDL, input types, and Java constructor/properties. |
| Data leaked in error message | Returning raw exception/invalid value to client | Normalize the message and only return filtered codes/paths. |

## 17. `@Validated` implementation checklist

1. Add a Bean Validation provider and ensure a `Validator` bean exists.
2. Use `jakarta.validation` with Spring Boot 3+.
3. Place `@Valid` on the argument if only the default group is needed.
4. Place `@Validated(Group.class)` on GraphQL parameters requiring group-based validation.
5. Declare groups clearly by use case and decide how `Default` is inherited.
6. Add `@Valid` to nested objects/collections to cascade validation.
7. Use SDL for types, requiredness, and nullability; use Bean Validation for value rules.
8. Keep critical business rules and authorization in the service/domain.
9. Normalize `ConstraintViolationException` into client-safe GraphQL errors.
10. Test groups, nested validation, binding errors, and verifying the service does not run on invalid input.

`@Validated` helps Spring for GraphQL apply the right set of constraints for each use case. By combining a validator bean, validation groups, `@Valid` cascading, and clear GraphQL error handling, controllers can reject invalid inputs before running business logic while keeping the schema and client contract easy to understand.

References: [Spring for GraphQL — Annotated Controllers, Validation](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.validation), [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html), and [Spring `@Validated` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/annotation/Validated.html).
