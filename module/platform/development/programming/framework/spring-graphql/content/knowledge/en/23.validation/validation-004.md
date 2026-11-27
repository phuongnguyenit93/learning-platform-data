# ConstraintViolationException

In Spring for GraphQL, input data is typically bound from GraphQL arguments into Java objects and then checked with Jakarta Bean Validation. For example, a book creation mutation might require the title not to be blank, the ISBN to match a valid format, and the publication year to fall within a valid range. When one or more constraints are not satisfied, Bean Validation can raise **ConstraintViolationException**.

ConstraintViolationException contains a set of ConstraintViolation instances describing each violated rule. Spring for GraphQL can convert this exception into GraphQL errors through its exception resolution mechanism. As a result, clients receive structured error messages without the server exposing stack traces or internal details.

## At which stage does ConstraintViolationException appear?

A GraphQL request goes through several steps before the resolver returns data:

~~~mermaid
flowchart TD
    A["GraphQL document and variables"] --> B["Parse and validate operation"]
    B --> C["Coerce scalars and enums"]
    C --> D["Bind arguments into Java objects"]
    D --> E["Bean Validation"]
    E --> F["Invoke controller resolver"]
    F --> G["Service and domain logic"]
    G --> H["GraphQL response"]
    E --> X["ConstraintViolationException"]
    X --> Y["GraphQL exception resolver"]
    Y --> H
~~~

ConstraintViolationException typically appears at the Bean Validation step, after GraphQL has accepted the data types and Spring has bound the arguments into Java objects, but before the controller method is invoked successfully.

This differs from the following errors:

| Error type | Timing | Example |
| --- | --- | --- |
| GraphQL parse/validation error | Before resolver execution | Syntax error, non-existent field, missing non-null argument |
| Scalar coercion error | When GraphQL converts inputs | Passing a string into an Int argument or an invalid enum value |
| Argument binding error | When Spring converts an argument map into a Java object | Unable to instantiate DTO or convert a property |
| ConstraintViolationException | When Bean Validation checks an object or method parameter | blank title, quantity less than 1 |
| Domain exception | Inside service or domain logic | Product does not exist, user lacks permission |

Properly distinguishing the error source helps choose the right place to handle it. ConstraintViolationException is not a GraphQL syntax error and is not synonymous with an argument binding error.

## Bean Validation in annotated controllers

Spring for GraphQL supports Bean Validation for annotated controller methods when the application has a Validator bean. Typically, Spring Boot creates a LocalValidatorFactoryBean when the validation dependency is on the classpath.

With Gradle, you can add the starter:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
~~~

If the project configures validation manually, ensure a Jakarta Validation provider such as Hibernate Validator and a compatible Validator bean are present. Spring for GraphQL uses the configured validator to check controller parameters that have the appropriate annotations.

## Declaring constraints on an input DTO

Suppose the API has a mutation to create a book:

~~~graphql
type Mutation {
  createBook(input: CreateBookInput!): Book!
}

input CreateBookInput {
  title: String!
  isbn: String!
  publishedYear: Int!
}

type Book {
  id: ID!
  title: String!
  isbn: String!
  publishedYear: Int!
}
~~~

A Java record can declare constraints directly on its components:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreateBookInput(
        @NotBlank(message = "Title must not be blank")
        @Size(max = 150, message = "Title must not exceed 150 characters")
        String title,

        @NotBlank(message = "ISBN must not be blank")
        @Pattern(
                regexp = "[0-9Xx-]{10,17}",
                message = "ISBN format is invalid")
        String isbn,

        @NotNull(message = "Published year is required")
        @Min(value = 1450, message = "Published year is invalid")
        @Max(value = 2100, message = "Published year is invalid")
        Integer publishedYear) {
}
~~~

The regular expression above only checks length and allowed character groups; it does not verify the structure or checksum of ISBN-10/ISBN-13. If full ISBN verification is needed, use a custom constraint validator or a dedicated library.

Some common constraints:

| Constraint | Purpose |
| --- | --- |
| @NotNull | Value must not be null |
| @NotBlank | String must contain at least one non-whitespace character |
| @NotEmpty | String, collection, or map must not be empty |
| @Size | Limits string length or element count |
| @Min, @Max | Limits numeric values |
| @Positive, @PositiveOrZero | Checks positive or non-negative numbers |
| @Email | Checks email format |
| @Pattern | Validates a string against a regular expression |

Choose constraints that match the meaning of the data. For example, @NotBlank fits title, whereas @NotNull fits a required integer. With a nullable Integer, @Min alone does not make a null value invalid; combine it with @NotNull if the field is required.

## Enabling validation with @Valid

Mark the input parameter with @Valid to instruct Spring for GraphQL to check constraints before calling the resolver:

~~~java
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
    public Book createBook(@Argument @Valid CreateBookInput input) {
        return bookService.create(input);
    }
}
~~~

When the input is valid, the createBook method is called. If any constraint is violated, Spring does not execute the method body as a normal call and instead raises ConstraintViolationException. Because of this, the service does not have to receive an already-invalid object just to re-check basic constraints.

@Valid also handles cascade validation: if a DTO contains a child object, the validator checks the child object when the property is marked with @Valid.

~~~java
public record AuthorInput(
        @NotBlank String name,
        @Email String email) {
}

public record CreateBookInput(
        @NotBlank String title,
        @NotNull @Valid AuthorInput author) {
}
~~~

For collections of nested objects, you can use container element validation:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        @NotEmpty List<@Valid AuthorInput> authors) {
}
~~~

In that case, the validator checks both the constraint on the list and the constraints of each AuthorInput element.

## Distinguishing @Valid and @Validated

@Valid is a Jakarta Validation annotation, commonly used to trigger validation and cascade into nested objects. Spring provides @Validated to specify validation groups.

Example:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.validation.annotation.Validated;

public interface CreateChecks {
}

public interface UpdateChecks {
}

public record BookInput(
        @NotBlank(groups = {CreateChecks.class, UpdateChecks.class})
        String title,

        @NotBlank(groups = CreateChecks.class)
        String isbn) {
}
~~~

The resolver can choose the appropriate group:

~~~java
@MutationMapping
public Book createBook(
        @Argument @Validated(CreateChecks.class) BookInput input) {
    return bookService.create(input);
}
~~~

Configure and test validation groups according to the Spring for GraphQL and Jakarta Validation provider versions in use. If groups are not needed, @Valid is simpler and easier to read.

## What information does ConstraintViolationException contain?

ConstraintViolationException provides a set of ConstraintViolation objects. Each violation describes an unsatisfied constraint, typically including:

- propertyPath: the path to the invalid property or parameter.
- message: the resolved validation message.
- messageTemplate: the message template before interpolation.
- invalidValue: the invalid value.
- rootBeanClass: the type of the validated bean.
- constraintDescriptor: metadata of the constraint.

You can read violations in Java:

~~~java
catch (ConstraintViolationException exception) {
    for (ConstraintViolation<?> violation
            : exception.getConstraintViolations()) {
        String field = violation.getPropertyPath().toString();
        String message = violation.getMessage();
        // Record field and message according to logging policy
    }
}
~~~

In GraphQL handling, avoid sending the raw invalidValue back to the client. That value may contain emails, phone numbers, tokens, or sensitive data. Usually you only need to return a normalized field path and an appropriate message.

## Converting ConstraintViolationException to GraphQL errors

Spring for GraphQL provides @GraphQlExceptionHandler for annotated controllers. A handler can live inside the controller itself to handle exceptions from resolvers in that controller, or inside @ControllerAdvice to be shared across multiple controllers.

Example global handler:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

import java.util.List;
import java.util.Map;

@ControllerAdvice
public class GraphQlValidationExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handle(
            ConstraintViolationException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        List<Map<String, String>> violations =
                exception.getConstraintViolations().stream()
                        .map(this::toClientViolation)
                        .toList();

        return errorBuilder
                .errorType(ErrorType.BAD_REQUEST)
                .message("Invalid input data")
                .extensions(Map.of("violations", violations))
                .build();
    }

    private Map<String, String> toClientViolation(
            ConstraintViolation<?> violation) {
        return Map.of(
                "field", violation.getPropertyPath().toString(),
                "message", violation.getMessage());
    }
}
~~~

GraphqlErrorBuilder is prepared by Spring according to the current DataFetchingEnvironment. Therefore, the error can carry the field path and location corresponding to the resolver that caused the error. ErrorType.BAD_REQUEST classifies the error at the GraphQL layer; it does not mean every HTTP transport must return status 400.

Example response:

~~~json
{
  "data": {
    "createBook": null
  },
  "errors": [
    {
      "message": "Invalid input data",
      "path": ["createBook"],
      "extensions": {
        "classification": "BAD_REQUEST",
        "violations": [
          {
            "field": "createBook.input.title",
            "message": "Title must not be blank"
          },
          {
            "field": "createBook.input.isbn",
            "message": "ISBN format is invalid"
          }
        ]
      }
    }
  ]
}
~~~

The exact propertyPath depends on how controller parameters and input objects are bound. If you want a stable response for the frontend, normalize field names into public input paths instead of promising that internal propertyPaths always have the exact same format.

## Distinguishing validation errors and binding errors

GraphQlArgumentBinder can raise BindException when it cannot instantiate or populate a Java object. Bean Validation raises ConstraintViolationException when the object has already been bound but fails to satisfy constraints.

Example:

- Client sends publishedYear as a string that cannot be converted to Int: GraphQL coercion error.
- GraphQL input is valid, but the Java constructor cannot bind a property: argument binding error.
- The Java object is created, but title is blank: ConstraintViolationException.
- Title is valid, but ISBN is already used by another book: domain exception or persistence error depending on design.

Do not use one handler for every exception and return the exact same message. BindException may need to return an input structure error; ConstraintViolationException needs to return a list of constraints; domain exceptions need classification by business rules.

## Handling errors when not using annotated controllers

@GraphQlExceptionHandler applies to exceptions from annotated controller methods. If an exception comes from a directly registered DataFetcher or from another component that does not go through an annotated controller, you can use DataFetcherExceptionResolver.

Example:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import jakarta.validation.ConstraintViolationException;
import org.springframework.graphql.execution.DataFetcherExceptionResolverAdapter;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Component;

import java.util.List;

@Component
public class ValidationExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected List<GraphQLError> resolveToMultipleErrors(
            Throwable exception,
            graphql.schema.DataFetchingEnvironment environment) {

        if (!(exception instanceof ConstraintViolationException violationException)) {
            return null;
        }

        List<GraphQLError> errors =
                violationException.getConstraintViolations().stream()
                        .map(violation -> GraphqlErrorBuilder.newError(environment)
                                .errorType(ErrorType.BAD_REQUEST)
                                .message(violation.getMessage())
                                .build())
                        .toList();

        return errors;
    }
}
~~~

The resolver returns null when it does not handle an exception so the next resolver in the chain has a chance to handle it. If it takes responsibility, it returns a list of GraphQLError objects. Spring Boot auto-detects DataFetcherExceptionResolver beans and registers them with GraphQlSource.

Choose one clear place to handle each exception. Avoid creating multiple handlers that catch ConstraintViolationException simultaneously while returning different messages or extensions structures.

## Partial data and null propagation

GraphQL allows a response to contain both data and errors. When a field resolver fails due to validation, other fields in the same operation may still return data. However, the null value at the failing field follows the schema's nullability rules.

Example:

~~~graphql
type Query {
  profile: Profile
  searchBooks(input: BookSearchInput!): [Book!]!
}
~~~

If searchBooks raises a validation error, this field is treated as null. Because the schema declares [Book!]! as non-null, the null can propagate up to the Query root and turn data into null. If the field is declared nullable, sibling fields such as profile can still return results.

Therefore, nullability design directly affects how much remaining data survives when a resolver fails. Consider whether a field truly must be non-null in every situation.

## Validation in services and domains

Bean Validation in controllers is very useful for early feedback on invalid input. However, services may be called from REST endpoints, message consumers, schedulers, or tests without going through a GraphQL controller. Therefore, critical business invariants should not exist solely in GraphQL resolvers.

Responsibilities can be divided as follows:

- GraphQL SDL checks types, nullability, and operation structure.
- Bean Validation checks input data format and limits.
- Service/domain checks business rules that depend on current state.
- Database constraints protect final integrity such as unique keys, foreign keys, and not-null.

For example, @Size(max = 150) can limit title length, but only the database guarantees unique ISBN when multiple requests run concurrently. The service can check whether an ISBN already exists to return a friendly message, yet a unique constraint is still needed to prevent race conditions.

## Message localization and client notifications

Constraint messages can be declared directly:

~~~java
@NotBlank(message = "Title must not be blank")
String title
~~~

Or loaded from a Validation MessageSource:

~~~java
@NotBlank(message = "{book.title.required}")
String title
~~~

ValidationMessages.properties file:

~~~properties
book.title.required=Book title is required
book.isbn.invalid=ISBN format is invalid
~~~

When the application supports multiple languages, message interpolation can rely on the locale of the validation context. Determine how locale is passed from the GraphQL request to the validator if messages need to be returned in the client's language.

Messages sent to clients should be concise, actionable, and must not contain internal class names, SQL statements, stack traces, or secret values. Full exceptions can be logged in server logs with a correlation ID for diagnostics, without returning all of those details in the GraphQL response.

## Testing ConstraintViolationException

Spring for GraphQL provides GraphQlTester to test mutations and GraphQL errors. Valid input example:

~~~java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                id
                title
            }
        }
        """)
    .variable("input", Map.of(
            "title", "Spring GraphQL",
            "isbn", "978-1234567890",
            "publishedYear", 2025))
    .execute()
    .path("createBook.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL");
~~~

With invalid input:

~~~java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                id
            }
        }
        """)
    .variable("input", Map.of(
            "title", " ",
            "isbn", "invalid",
            "publishedYear", 2200))
    .execute()
    .errors()
    .satisfy(errors -> {
        assertThat(errors).hasSize(1);
        assertThat(errors.get(0).getMessage())
                .contains("Invalid input data");
        assertThat(errors.get(0).getExtensions())
                .containsKey("violations");
    });
~~~

Cases to test:

- Valid input is passed into the resolver.
- Each violated constraint produces appropriate error details.
- Multiple failing constraints are returned in a consistent structure.
- Nested objects and collections undergo cascade validation.
- Validation groups run properly according to the use case.
- Exception handler does not return invalidValue or sensitive data.
- Service is not invoked when validation fails.
- Domain errors are distinguished from constraint errors.
- Null propagation matches the SDL.

In addition to GraphQlTester, you can test DTOs directly with Validator to verify constraints independently of GraphQL. Integration tests are still necessary to confirm that Spring for GraphQL actually triggers validation and that the exception handler is registered.

## Common errors

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| @Valid does not produce validation errors | Missing Validator bean or missing validation provider | Add the validation starter and check Validator configuration |
| ConstraintViolationException is not converted into the expected error | Missing @GraphQlExceptionHandler or appropriate DataFetcherExceptionResolver | Check handler scope and exception chain |
| Invalid input still reaches the service | Validation is not enabled on the parameter | Check @Valid/@Validated and controller configurer |
| Nested object is not checked | Missing @Valid on the property or collection element | Add cascade validation |
| Null slips past @Min | @Min does not replace @NotNull | Combine with @NotNull if the field is required |
| Error response leaks input data | Putting invalidValue or the entire exception into extensions | Only return filtered field paths and messages |
| Handler does not catch errors from custom DataFetcher | @GraphQlExceptionHandler only applies to the annotated controller flow | Register a DataFetcherExceptionResolver |
| Frontend does not know which field failed | Only returning a single generic message | Add a violations list in extensions |
| Data unexpectedly becomes null | Non-null propagation from the failing field | Review nullability of the field and its parents |

## Principles for handling ConstraintViolationException

When implementing validation for Spring for GraphQL, remember:

1. **Enable Bean Validation properly.** Have a Validator bean and a Jakarta Validation-compatible provider.
2. **Place constraints on DTOs.** Use @Valid on resolver parameters to check inputs before calling the method.
3. **Use cascade validation.** Mark @Valid on nested objects and collection elements that need checking.
4. **Distinguish error sources.** Coercion, binding, constraint, and domain exceptions require appropriate handling.
5. **Convert exceptions to GraphQL errors.** Use @GraphQlExceptionHandler for annotated controllers or DataFetcherExceptionResolver for general data fetchers.
6. **Return safe error information.** Do not include invalidValue, tokens, stack traces, or internal details in responses.
7. **Keep invariants in the domain and database.** Validation at GraphQL does not replace business checks at other entry points.
8. **Test both responses and side effects.** Verify the resolver/service does not execute when input is invalid.
9. **Design nullability intentionally.** A validation error can trigger null propagation up to parent fields.

ConstraintViolationException represents that one or more Bean Validation rules were not satisfied. In Spring for GraphQL, the exception typically arises when a controller parameter annotated with @Valid is checked before the resolver runs. Use @GraphQlExceptionHandler or DataFetcherExceptionResolver to convert violations into structured GraphQL errors, distinguishing them from coercion, binding, and domain errors, while keeping returned details safe. This organization helps clients know which input to fix while protecting system data and consistency.

## References

- [Spring for GraphQL - Annotated Controllers: Validation and Exception Handling](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL - Request Execution and Exception Resolution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Framework - Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
