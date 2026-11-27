# Mutation Validation

## 1. Why Do Mutations Need Validation?

Mutations modify system state: creating a book, updating a profile, placing an order, or canceling a transaction. Invalid input can corrupt data, violate business rules, or produce states that other parts of the system cannot handle.

In GraphQL, the schema already validates the structure and data types of an operation. However, a GraphQL-type-valid value is not necessarily valid for business rules. For example, `title: String!` ensures the client passes a non-null string, but it does not ensure the string has content, is not too long, or does not duplicate an existing book.

With Spring for GraphQL, mutation validation should be organized across multiple layers: GraphQL validates the operation contract, Bean Validation checks input DTOs, the service layer enforces business rules, and the database enforces final constraints. Each layer addresses a distinct class of errors.

## 2. Distinguishing Validation Layers

| Layer | What does it check? | Example |
| --- | --- | --- |
| GraphQL parsing and validation | Operation syntax, field names, arguments, selection sets, and schema types | Non-existent field, missing required argument |
| Scalar coercion | Whether variable or literal values can convert to the declared scalar | Passing a string to an `Int!` argument |
| Bean Validation | Data constraints on input DTOs | String must not be blank, page count must be positive |
| Business validation | Rules depending on existing data and business state | Author does not exist, ISBN already used, order cannot be canceled |
| Database constraints | Data integrity on write | Unique keys, foreign keys, not-null constraints |

GraphQL validation and scalar coercion execute before the Mutation resolver is invoked. Bean Validation typically runs after Spring for GraphQL binds arguments into Java objects. Business validation runs in the service or domain layer. Database constraints remain necessary because two concurrent requests can both pass business checks before writing data.

Do not try to force every rule into SDL. The schema expresses types, nullability, and input structure; rules like maximum lengths, custom formats, uniqueness, or state transitions normally belong in Java and the database.

## 3. Declaring Inputs for Mutations

Group input data for a create operation into an `input object`. Example for creating a book:

```graphql
input CreateBookInput {
    title: String!
    isbn: String!
    authorId: ID!
    pageCount: Int!
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}

type Book {
    id: ID!
    title: String!
    isbn: String!
    pageCount: Int!
}
```

The schema specifies that `input`, `title`, `isbn`, `authorId`, and `pageCount` must be supplied with non-null values. `Int!` also requires values within GraphQL's 32-bit integer range. Rules such as `title` not containing only whitespace or `pageCount` being greater than 0 require additional validation.

Client sends the mutation:

```graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
        isbn
        pageCount
    }
}
```

Variables:

```json
{
  "input": {
    "title": "Spring for GraphQL",
    "isbn": "9780000000042",
    "authorId": "author-7",
    "pageCount": 320
  }
}
```

If the client omits `title` or sends `null` for `title: String!`, GraphQL rejects the request per the schema. If it sends `pageCount` as a string, scalar coercion rejects it before the resolver executes.

## 4. Adding Bean Validation to the Project

With Spring Boot, add the validation starter to enable Jakarta Bean Validation integration. Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
```

The examples below use `jakarta.validation.*`, suitable for Spring Boot 3 and later. Spring Boot 2 projects use the `javax.validation.*` namespace; choose the package matching your Spring version and avoid mixing both namespaces in one application.

## 5. Placing Constraints on Input DTOs

Create a Java record matching `CreateBookInput`:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreateBookInput(
    @NotBlank(message = "Title must not be blank")
    @Size(max = 200, message = "Title must not exceed 200 characters")
    String title,

    @NotBlank(message = "ISBN must not be blank")
    @Pattern(
        regexp = "[0-9-]{10,17}",
        message = "ISBN must contain 10 to 17 digits or hyphens"
    )
    String isbn,

    @NotBlank(message = "Author ID must not be blank")
    String authorId,

    @NotNull(message = "Page count is required")
    @Min(value = 1, message = "Page count must be greater than 0")
    @Max(value = 10000, message = "Page count must not exceed 10000")
    Integer pageCount
) {
}
```

Commonly used annotations:

| Constraint | Purpose |
| --- | --- |
| `@NotNull` | Value must not be `null` |
| `@NotBlank` | String must be non-null and contain at least one non-whitespace character |
| `@NotEmpty` | String or collection must not be empty |
| `@Size(min, max)` | Limits string length or collection size |
| `@Min`, `@Max` | Limits numeric values |
| `@Positive`, `@PositiveOrZero` | Requires positive or non-negative numbers |
| `@Pattern` | Validates a string against a regular expression |
| `@Email` | Validates a string according to the provider's email rules |

Use wrappers like `Integer` for potentially missing values so `@NotNull` can catch null cases. Java primitives like `int` cannot represent null. Even when SDL already declares `Int!`, blocking null before Bean Validation runs, `@NotNull` remains helpful when the DTO is reused in other flows or to keep constraints explicit in Java.

The ISBN regular expression in this example only illustrates basic input formatting. If you need ISBN-10 or ISBN-13 checksum verification, use a dedicated validator rather than treating this regex as full ISBN validation.

## 6. Enabling Validation with `@Valid` in `@MutationMapping`

Spring for GraphQL supports validation on controller-bound arguments. Place `@Valid` on the `@Argument` parameter to trigger Bean Validation on the DTO before invoking the mutation logic:

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
    public Book createBook(@Argument("input") @Valid CreateBookInput input) {
        return bookService.create(input);
    }
}
```

When the DTO violates a constraint, Spring for GraphQL does not proceed with invoking the mutation method as a normal creation. The validation exception flows into the GraphQL error handling mechanism. Decide how to present errors to clients—such as mapping to a GraphQL error with a code and list of field errors, or explicitly returning a payload containing structured validation errors.

`@Valid` enables constraint checks on the bound object. For nested objects, place `@Valid` on child properties to cascade validation down into those objects.

## 7. Validating Nested Inputs and Lists

Mutations may accept complex structures, such as creating a book along with its chapters. Schema:

```graphql
input ChapterInput {
    title: String!
    sequence: Int!
}

input CreateBookWithChaptersInput {
    title: String!
    chapters: [ChapterInput!]!
}

type Mutation {
    createBookWithChapters(input: CreateBookWithChaptersInput!): Book!
}
```

Java DTOs:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.util.List;

public record ChapterInput(
    @NotBlank(message = "Chapter title must not be blank")
    @Size(max = 150, message = "Chapter title must not exceed 150 characters")
    String title,

    @NotNull
    @Positive(message = "Chapter sequence must be greater than 0")
    Integer sequence
) {
}

public record CreateBookWithChaptersInput(
    @NotBlank
    @Size(max = 200)
    String title,

    @NotEmpty(message = "Book must have at least one chapter")
    List<@NotNull @Valid ChapterInput> chapters
) {
}
```

`@Valid` on the list element instructs validation to cascade into each `ChapterInput`. `@NotEmpty` verifies the list has at least one element. `@NotNull` on the element prevents null items from entering the DTO in binding flows that might produce them.

If you only put `@Valid` on the mutation parameter without cascading validation on nested properties, constraints inside child objects may not run as expected. Test the first element, last element, and an empty list.

## 8. Business Validation in the Service or Domain Layer

Bean Validation fits constraints on a single input object: non-blank, length, numeric bounds, or format. Rules that depend on existing state must be checked in the service or domain layer.

For example, when creating a book:

- Whether the author exists.
- Whether the ISBN is already used by another book.
- Whether the current user has permission to create a book in this library.
- Whether the library is currently accepting new books.

Illustrative service:

```java
public Book create(CreateBookInput input) {
    Author author = authorRepository.findById(input.authorId())
        .orElseThrow(() -> new AuthorNotFoundException(input.authorId()));

    if (bookRepository.existsByIsbn(input.isbn())) {
        throw new DuplicateIsbnException(input.isbn());
    }

    Book book = Book.create(
        input.title().trim(),
        input.isbn(),
        author,
        input.pageCount()
    );

    return bookRepository.save(book);
}
```

This example assumes domain exceptions are defined in the application. Checking ISBN before saving improves business error messages, but it does not replace a database unique constraint. Two concurrent requests could both observe that the ISBN does not yet exist; the database must act as the final guarantor of uniqueness.

For operations modifying multiple tables or aggregates, define transaction boundaries in the service. If a validation or persistence step fails, data must roll back according to the business transaction policy.

## 9. Choosing How to Return Validation Errors to Clients

There are two common ways to represent validation errors in GraphQL. Choose based on your API contract and client experience.

### Approach A: Returning GraphQL errors

This fits well when validation exceptions are treated as field execution errors. The response may include `data` and `errors`, for example:

```json
{
  "data": null,
  "errors": [
    {
      "message": "Invalid input data",
      "path": ["createBook"],
      "extensions": {
        "code": "BAD_REQUEST",
        "fieldErrors": [
          {
            "field": "title",
            "message": "Title must not be blank"
          }
        ]
      }
    }
  ]
}
```

In this example, the `createBook` field is declared non-null (`Book!`). When the resolver raises an error, null propagation bubbles null up to the root, making `data` equal `null`. If the field returns nullable `Book`, the response can retain the `data` object and set only `createBook` to `null`.

Clients inspect `errors` and `extensions` to display per-field errors. Do not rely solely on HTTP status codes; GraphQL responses follow their own rules, and clients need to inspect both `data` and `errors`.

### Approach B: Returning a typed payload

If business errors are expected outcomes that clients handle as a normal branch, you can include validation errors in the output type:

```graphql
type ValidationError {
    field: String!
    message: String!
}

type CreateBookPayload {
    book: Book
    validationErrors: [ValidationError!]!
}

type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
}
```

The resolver can invoke `Validator` to collect constraint violations and convert them into `ValidationError`:

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.List;

public CreateBookPayload createBook(CreateBookInput input) {
    var violations = validator.validate(input);

    if (!violations.isEmpty()) {
        List<ValidationError> errors = violations.stream()
            .map(violation -> new ValidationError(
                violation.getPropertyPath().toString(),
                violation.getMessage()
            ))
            .toList();

        return new CreateBookPayload(null, errors);
    }

    Book book = bookService.create(input);
    return new CreateBookPayload(book, List.of());
}
```

This example assumes `Validator`, `ValidationError`, and `CreateBookPayload` are injected or defined accordingly. With this approach, do not put `@Valid` on the parameter if you want to receive violations from `Validator` and wrap them into the payload manually; if `@Valid` throws an exception before the method runs, your manual branch will never execute.

Typed payloads help clients clearly separate successful results from expected validation errors. However, agree on a consistent convention: when `validationErrors` is non-empty, `book` is null; on success, `validationErrors` is empty. Unexpected system errors should still go through GraphQL `errors`, rather than posing as validation errors.

## 10. Mapping Validation Exceptions to GraphQL Errors

If you choose Approach A, handle `MethodArgumentNotValidException` using `@GraphQlExceptionHandler` inside a controller or a GraphQL `@ControllerAdvice`.

Local handler example:

```java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import java.util.List;
import java.util.Map;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.MethodArgumentNotValidException;

@GraphQlExceptionHandler
public GraphQLError handleValidation(
        MethodArgumentNotValidException exception,
        DataFetchingEnvironment environment) {

    List<Map<String, String>> fieldErrors = exception.getBindingResult()
        .getFieldErrors()
        .stream()
        .map(error -> Map.of(
            "field", error.getField(),
            "message", error.getDefaultMessage() == null
                ? "Invalid value"
                : error.getDefaultMessage()
        ))
        .toList();

    return GraphqlErrorBuilder.newError(environment)
        .errorType(ErrorType.BAD_REQUEST)
        .message("Invalid input data")
        .extensions(Map.of("fieldErrors", fieldErrors))
        .build();
}
```

This snippet illustrates converting field errors into structured extensions. Confirm the actual exception thrown by your Spring for GraphQL version and adjust the handler for the exact exception type produced by argument validation. You can also handle domain exceptions such as `DuplicateIsbnException` or `AuthorNotFoundException` with dedicated handlers.

Include only helpful and safe information in responses. Never return stack traces, SQL statements, table names, connection details, or sensitive input content. Technical diagnostics should be logged internally with a correlation ID.

## 11. Testing Mutation Validation with `GraphQlTester`

Test schema-invalid operations, constraint-violating inputs, business rule failures, and valid cases. Example testing Bean Validation with `GraphQlTester`:

```java
@SpringBootTest
@AutoConfigureHttpGraphQlTester
class CreateBookMutationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void rejectsBlankTitle() {
        graphQlTester.document("""
            mutation CreateBook($input: CreateBookInput!) {
                createBook(input: $input) {
                    id
                    title
                }
            }
            """)
            .variable("input", Map.of(
                "title", "   ",
                "isbn", "9780000000042",
                "authorId", "author-7",
                "pageCount", 320
            ))
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).anySatisfy(error ->
                assertThat(error.getMessage())
                    .contains("Invalid input data")
            ));
    }
}
```

This example assumes a handler maps validation exceptions to the message shown earlier and the test context configures the required services. For typed payload APIs, instead of asserting on `errors`, verify that `validationErrors` contains the expected field and message.

Key test cases:

- Missing required input or wrong scalar type: rejected by GraphQL before calling the resolver.
- Empty or whitespace-only string: rejected by Bean Validation.
- Out-of-bounds value: rejected by Bean Validation.
- Nested input object or list with invalid elements: caught by cascade validation.
- Non-existent author or duplicate ISBN: business validation returns the appropriate error.
- Two requests creating the same identifier: database constraint still protects integrity.
- Valid input: mutation calls the service and returns accurate data.
- Validation failure: verify no new record was persisted.

Do not assert solely on the message. Verify the error path, extension code or `fieldErrors`, and confirm that the service/repository performs no data writes when input is invalid.

## 12. Common Pitfalls in Mutation Validation

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `@Valid` does not catch constraints | Missing `spring-boot-starter-validation` or missing `@Valid` on the argument | Verify dependency, provider, and `@Valid` placement |
| Whitespace-only strings pass validation | Used `@NotNull` or `@NotEmpty` instead of `@NotBlank` | Use `@NotBlank` for strings requiring content |
| Nested object constraints do not run | Missing cascading `@Valid` on properties or elements | Add `@Valid` in the right places and test nested inputs |
| Wrong-type values never reach the resolver | GraphQL scalar coercion rejects them before method invocation | Check SDL, scalars, and variable types |
| Uniqueness checks still create duplicates under load | Only checking via an `exists` query before saving | Add a database unique constraint and map constraint errors |
| Validation exceptions return generic confusing errors | Field errors are not mapped or error codes are unstandardized | Use `@GraphQlExceptionHandler` or typed payloads |
| Clients fail to show per-field errors | Not reading `errors.extensions` or `validationErrors` | Standardize the response contract and update clients |
| Error messages leak internal data | Returning raw exceptions or persistence details | Return safe messages only; log details internally |
| Resolver manually validates while also blocked by `@Valid` | Mixing exception-based and typed-payload strategies | Choose one clear validation flow per mutation |

## 13. Mutation Validation Design Checklist

- [ ] Input objects in SDL accurately reflect structure and nullability.
- [ ] Scalar coercion and GraphQL document validation are understood as the first validation layer.
- [ ] Java DTOs declare constraints matching data rules.
- [ ] `spring-boot-starter-validation` is included when using Bean Validation.
- [ ] `@Valid` is placed on `@Argument` or validation is invoked explicitly.
- [ ] Nested objects and collection elements have cascading validation where needed.
- [ ] Business rules are enforced in the service/domain layer.
- [ ] The database has required unique, foreign key, and check constraints to protect data.
- [ ] Either GraphQL errors or typed payloads are chosen consistently for validation errors.
- [ ] Error responses contain no stack traces or internal details.
- [ ] Tests cover invalid inputs, failed business rules, success paths, and data integrity.

## Conclusion

Mutation validation requires coordinating multiple layers. GraphQL validates operations and scalars against the schema; Bean Validation checks constraints on input DTOs; the service/domain layer enforces business rules; and the database protects integrity during concurrent writes.

In Spring for GraphQL, you can place `@Valid` on `@Argument` parameters of `@MutationMapping` methods to trigger Bean Validation. Then choose an appropriate way to present errors: mapping exceptions to GraphQL errors with `extensions`, or returning a typed payload for expected business errors. With a standardized response contract and thorough `GraphQlTester` coverage, clients can display accurate errors while the server avoids persisting invalid data.
