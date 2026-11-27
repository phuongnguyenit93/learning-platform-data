# Validation on `@Arguments`

## 1. What is `@Arguments` used for?

A GraphQL field can accept multiple independent arguments, such as a search keyword, author ID, page range, and publication status. When using `@Argument`, the controller receives each argument individually or receives an object from a single structured argument. When you want to group **all arguments of the current field** into one Java object, Spring for GraphQL provides the `@Arguments` annotation.

For example, a schema has the field:

```graphql
type Query {
    searchBooks(
        keyword: String!
        authorId: ID
        minPages: Int
        maxPages: Int
    ): [Book!]!
}
```

The method can receive all four arguments into a single DTO:

```java
@QueryMapping
public List<Book> searchBooks(@Arguments SearchBooksArguments arguments) {
    return bookQueryService.search(arguments);
}
```

`@Arguments` takes the argument map of the `searchBooks` field and binds the top-level values into the corresponding properties of `SearchBooksArguments`. As a result, the resolver signature is cleaner when a field has many filter criteria, and it becomes easy to apply Bean Validation on a clearly typed object.

`@Arguments` only represents the arguments of the field currently being resolved. It does not retrieve all operation variables, does not include the selection set, and does not automatically read arguments of parent or other child fields.

## 2. Distinguishing `@Arguments` and `@Argument`

The two annotations serve different purposes:

| Declaration | Bound data |
| --- | --- |
| `@Argument SearchBooksInput input` | Value of a single argument named `input` as a `SearchBooksInput` object |
| `@Argument("keyword") String keyword` | Value of the single `keyword` argument |
| `@Arguments SearchBooksArguments arguments` | All arguments of the field as a `SearchBooksArguments` object |
| `@Arguments Map<String, Object> arguments` | Raw map containing all arguments of the field |
| `@Argument Map<String, Object> filter` | Raw value of a single argument named `filter` |

Example of two schemas with different structures:

**A single input object argument:**

```graphql
input BookSearchInput {
    keyword: String!
    authorId: ID
}

type Query {
    searchBooks(input: BookSearchInput!): [Book!]!
}
```

Resolver using `@Argument`:

```java
@QueryMapping
public List<Book> searchBooks(@Argument("input") BookSearchInput input) {
    return bookQueryService.search(input);
}
```

**Multiple arguments at the field level:**

```graphql
type Query {
    searchBooks(keyword: String!, authorId: ID): [Book!]!
}
```

Resolver using `@Arguments`:

```java
@QueryMapping
public List<Book> searchBooks(@Arguments SearchBooksArguments arguments) {
    return bookQueryService.search(arguments);
}
```

Do not use `@Arguments` to bind a single argument named `input`. For that structure, use `@Argument("input")`. Conversely, if the schema declares multiple separate arguments at the field level, `@Arguments` helps group them into one object.

## 3. How Spring binds all arguments into a DTO

Spring for GraphQL uses `GraphQlArgumentBinder` to instantiate and populate method parameters. When a parameter is marked with `@Arguments`, the binder takes the entire argument map of the field and binds top-level keys into the constructor or properties of the target object.

Example DTO as a Java record:

```java
public record SearchBooksArguments(
    String keyword,
    String authorId,
    Integer minPages,
    Integer maxPages) {
}
```

With the operation:

```graphql
query SearchBooks(
    $keyword: String!
    $authorId: ID
    $minPages: Int
    $maxPages: Int
) {
    searchBooks(
        keyword: $keyword
        authorId: $authorId
        minPages: $minPages
        maxPages: $maxPages
    ) {
        id
        title
    }
}
```

and variables:

```json
{
  "keyword": "spring",
  "authorId": "author-7",
  "minPages": 100,
  "maxPages": 500
}
```

The binder creates `SearchBooksArguments` with the corresponding properties. For Java records, Spring can use the canonical constructor. For regular classes, the binder can also use a matching constructor or default constructor combined with setters. Binding of nested objects is performed recursively.

GraphQL argument names must match property or constructor parameter names according to the active binding rules. If the project uses a different naming convention, you can configure `GraphQlArgumentBinder.Options` via `AnnotatedControllerConfigurer`.

## 4. Declaring constraints on a DTO used with `@Arguments`

After binding into a typed object, you can use Jakarta Bean Validation to check data constraints.

Example book search DTO:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public record SearchBooksArguments(
    @NotBlank(message = "Search keyword must not be blank")
    @Size(max = 100, message = "Keyword must not exceed 100 characters")
    String keyword,

    @Size(max = 64, message = "Author ID must not exceed 64 characters")
    String authorId,

    @Min(value = 1, message = "Minimum pages must be greater than 0")
    Integer minPages,

    @Min(value = 1, message = "Maximum pages must be greater than 0")
    @Max(value = 10000, message = "Maximum pages must not exceed 10000")
    Integer maxPages) {
}
```

Common constraints:

| Constraint | Purpose |
| --- | --- |
| `@NotNull` | Value must not be null |
| `@NotBlank` | String must have at least one non-whitespace character |
| `@NotEmpty` | String or collection must not be empty |
| `@Size` | Limits string length or collection element count |
| `@Min`, `@Max` | Limits numeric values |
| `@Positive`, `@PositiveOrZero` | Checks positive or non-negative numbers |
| `@Pattern` | Validates a string against a regular expression |
| `@Email` | Checks email format according to the validation provider |

Prefer wrapper types such as `Integer` when an argument may be omitted or null. Java primitives like `int` cannot represent null. Even if the schema declares an `Int!` argument—so GraphQL already guarantees the argument is non-null before calling the resolver—Bean Validation is still useful to check value domains such as requiring a positive number.

## 5. Enabling Bean Validation on `@Arguments`

Place `@Valid` on the same method parameter as `@Arguments`:

```java
import jakarta.validation.Valid;
import org.springframework.graphql.data.method.annotation.Arguments;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookQueryService bookQueryService;

    public BookQueryController(BookQueryService bookQueryService) {
        this.bookQueryService = bookQueryService;
    }

    @QueryMapping
    public List<Book> searchBooks(
            @Arguments @Valid SearchBooksArguments arguments) {
        return bookQueryService.search(arguments);
    }
}
```

When Spring for GraphQL detects a Bean Validation `Validator` in the application context, `AnnotatedControllerConfigurer` enables validation for annotated controller methods. If the object violates a constraint, a validation exception is thrown before the resolver method is called.

`@Valid` marks the object to check constraints on. It does not create a validator by itself. The application needs a Bean Validation provider and a `Validator` bean, usually configured through the Spring Boot validation starter.

With Spring Boot 3 and above, use the `jakarta.validation` namespace. Older Spring Boot 2 projects typically use `javax.validation`; do not mix the two namespaces in the same configuration.

## 6. Adding the validation dependency

With Spring Boot, add the starter to include a Bean Validation provider and Spring integration:

Maven:

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

Spring Boot usually auto-configures `LocalValidatorFactoryBean` when the appropriate dependency is present. If the application manages validation manually, register a bean implementing `jakarta.validation.Validator` so `AnnotatedControllerConfigurer` can detect and use it.

If a DTO has annotations without a validator provider, constraints may not be enforced. Check dependencies, validation beans, and controller configuration before concluding that `@Valid` is not working.

## 7. Validating nested objects

A field can receive arguments containing nested input objects. `@Arguments` binds top-level arguments into the DTO; for each child property, cascade validation with `@Valid` is required.

SDL:

```graphql
input BookFilter {
    keyword: String
    authorId: ID
}

input PageRange {
    min: Int
    max: Int
}

type Query {
    searchBooks(filter: BookFilter!, pageRange: PageRange): [Book!]!
}
```

DTO:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

public record SearchBooksArguments(
    @NotNull(message = "Filter is required")
    @Valid
    BookFilter filter,

    @Valid
    PageRange pageRange) {
}

public record BookFilter(
    @NotBlank(message = "Keyword must not be blank")
    String keyword,

    @Size(max = 64)
    String authorId) {
}

public record PageRange(
    @Min(1)
    Integer min,

    @Min(1)
    Integer max) {
}
```

When `@Valid` is placed on the `filter` and `pageRange` properties, Bean Validation descends into the child objects to check constraints. Without cascade validation, constraints inside nested objects may not run.

For nested collections, use cascade validation on elements:

```java
public record BulkSearchArguments(
    @NotEmpty
    List<@NotNull @Valid BookFilter> filters) {
}
```

`@NotEmpty` checks that the collection has at least one element; `@NotNull` and `@Valid` check each element and the constraints inside that element.

## 8. Validating rules across multiple arguments

Some rules cannot be checked independently on each field. For example, `minPages` must not be greater than `maxPages`. You can check this at the class level using a custom constraint or a validation method recognized by Bean Validation.

Example using `@AssertTrue`:

```java
import jakarta.validation.constraints.AssertTrue;

public record SearchBooksArguments(
    @NotBlank String keyword,
    Integer minPages,
    Integer maxPages) {

    @AssertTrue(message = "Minimum pages must not exceed maximum pages")
    public boolean isPageRangeValid() {
        return minPages == null
            || maxPages == null
            || minPages <= maxPages;
    }
}
```

The rule is checked across the whole object because it needs both values at once. For more complex business logic, create a custom class-level constraint consisting of an annotation and a `ConstraintValidator` so the error can be attached to the appropriate field.

Bean Validation only verifies the validity of input data against declared rules. Database-dependent rules such as whether an author exists, whether a book belongs to the current tenant, or whether an ISBN is unique should still be checked in the service/domain layer and protected by database constraints when needed.

## 9. Using `@Validated` to select validation groups

If the same DTO is used for multiple operations with different rule sets, you can declare validation groups.

Define groups:

```java
public interface BasicSearch {
}

public interface AdvancedSearch extends BasicSearch {
}
```

Constraints by group:

```java
public record SearchBooksArguments(
    @NotBlank(groups = BasicSearch.class)
    String keyword,

    @Size(max = 64, groups = AdvancedSearch.class)
    String authorId) {
}
```

Select the group on the method parameter:

```java
import org.springframework.validation.annotation.Validated;

@QueryMapping
public List<Book> searchBooks(
        @Arguments @Validated(AdvancedSearch.class)
        SearchBooksArguments arguments) {
    return bookQueryService.search(arguments);
}
```

In the example, `AdvancedSearch` extends `BasicSearch`, so selecting `AdvancedSearch` also runs constraints belonging to `BasicSearch`. Constraints without a declared group belong to `Default`; if `Default` also needs to run, have the custom group extend `Default` or configure an appropriate group sequence.

Do not add validation groups if all operations share the same rules. For a single-purpose DTO, `@Valid` is usually simpler and easier to read.

## 10. Using `@Arguments Map` and limitations of automatic validation

`@Arguments` can also accept `Map<String, Object>` to get a raw map of all arguments:

```java
@QueryMapping
public List<Book> searchBooks(@Arguments Map<String, Object> arguments) {
    String keyword = (String) arguments.get("keyword");
    return bookQueryService.search(keyword);
}
```

This approach is useful when dynamic handling or building a generic adapter is needed, but a raw map has no bean structure and does not automatically carry constraints like `@NotBlank`, `@Min`, or `@Size`. Placing `@Valid` on `Map<String, Object>` does not automatically turn map keys into DTO properties with constraints.

When automatic validation is needed, prefer a typed DTO:

```java
@QueryMapping
public List<Book> searchBooks(@Arguments @Valid SearchBooksArguments arguments) {
    return bookQueryService.search(arguments);
}
```

If receiving a raw map is unavoidable, convert it to a typed DTO or call `Validator` explicitly after creating the appropriate object. Avoid casting directly from the map without checking, as type errors may only surface at runtime.

Version note: starting from Spring for GraphQL 1.2, `@Argument Map<String, Object>` retrieves the raw value of the correspondingly named argument; to retrieve the entire argument map of the field, use `@Arguments Map<String, Object>`.

## 11. Distinguishing GraphQL validation, binding, and Bean Validation

A request goes through several verification steps before business service processing:

| Step | Error example | Result |
| --- | --- | --- |
| GraphQL parse/validation | Non-existent field or missing non-null argument | Resolver is not called |
| Scalar coercion | Passing a string into an `Int` argument | GraphQL rejects input before binding DTO |
| Argument binding | Value cannot be converted to Java property or constructor mismatch | `BindException` with field errors |
| Bean Validation | `keyword` contains only whitespace or `minPages` less than 1 | Validation exception before calling method |
| Business validation | Author does not exist or user lacks permission to view tenant | Service/domain returns business error |
| Database constraint | Unique key violated by two concurrent requests | Persistence exception handled at data write layer |

These steps serve different purposes. For example, `keyword: String!` only guarantees a non-null value under GraphQL; `@NotBlank` checks that the string has content; only the service can check whether the keyword matches search rules or whether the user has permission to search within that data scope.

Do not use Bean Validation to replace GraphQL schema validation. Likewise, avoid putting all business rules into DTO constraints if those rules depend on system data or state.

## 12. Handling binding and validation errors in GraphQL responses

Under the annotated controller mechanism, if binding fails, `GraphQlArgumentBinder` throws `BindException` and accumulates errors by argument path. If Bean Validation detects constraint violations, a validation exception is thrown before the resolver method is called. According to Spring for GraphQL documentation, the Bean Validation case is typically represented by `ConstraintViolationException`.

You can standardize errors with `@GraphQlExceptionHandler` in a controller or `@ControllerAdvice` for GraphQL. Example handler:

```java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import jakarta.validation.ConstraintViolationException;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.validation.BindException;
import java.util.List;
import java.util.Map;

@GraphQlExceptionHandler
public GraphQLError handleBindingError(
        BindException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
        .message("Arguments have invalid format")
        .extensions(Map.of("code", "INVALID_ARGUMENTS"))
        .build();
}
```

For `ConstraintViolationException`, you can build a dedicated handler to return code `VALIDATION_FAILED` and a list of field errors:

```java
@GraphQlExceptionHandler
public GraphQLError handleConstraintViolation(
        ConstraintViolationException exception,
        DataFetchingEnvironment environment) {

    List<Map<String, String>> violations = exception.getConstraintViolations()
        .stream()
        .map(violation -> Map.of(
            "field", violation.getPropertyPath().toString(),
            "message", violation.getMessage()
        ))
        .toList();

    return GraphqlErrorBuilder.newError(environment)
        .message("Invalid arguments")
        .extensions(Map.of(
            "code", "VALIDATION_FAILED",
            "violations", violations
        ))
        .build();
}
```

The exact response structure depends on the application's error contract. Do not return stack traces, SQL queries, or internal details in messages sent to clients.

If shared handlers are needed across controllers, use `@ControllerAdvice`. If errors come from a `DataFetcher` that is not an annotated controller, handle them via an appropriate `DataFetcherExceptionResolver`.

Spring GraphQL annotated controllers do not use Spring MVC's `BindingResult` mechanism to hold errors next to parameters. Design exception handling in GraphQL to convert errors into `GraphQLError`.

## 13. Testing validation on `@Arguments` with `GraphQlTester`

Tests should send actual operations with multiple top-level arguments and verify that the resolver does not run when the DTO violates constraints.

Schema example:

```graphql
type Query {
    searchBooks(
        keyword: String!
        minPages: Int
        maxPages: Int
    ): [Book!]!
}
```

Resolver:

```java
@QueryMapping
public List<Book> searchBooks(
        @Arguments @Valid SearchBooksArguments arguments) {
    return bookQueryService.search(arguments);
}
```

Test with whitespace-only keyword:

```java
@SpringBootTest
@AutoConfigureHttpGraphQlTester
class SearchBooksValidationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void rejectsBlankKeyword() {
        graphQlTester.document("""
            query {
                searchBooks(keyword: "   ", minPages: 10) {
                    id
                    title
                }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).anySatisfy(error ->
                assertThat(error.getExtensions()).containsEntry(
                    "code", "VALIDATION_FAILED")
            ));
    }
}
```

The example assumes the application has registered the `ConstraintViolationException` handler as in the previous section and that the handler returns extension `code = VALIDATION_FAILED`. In real tests, assert stable error codes and field error extensions rather than relying entirely on message text.

Test cases to include:

- All arguments are valid and the resolver returns the expected result.
- Missing non-null argument: GraphQL rejects before the resolver is called.
- Empty or whitespace-only string: Bean Validation rejects.
- Negative or out-of-bounds number: numeric constraints reject.
- Nested input object violating constraints: cascade validation detects errors.
- Two arguments violating cross-field rules: class-level validation detects errors.
- Argument cannot be bound to Java type: test BindException.
- Using validation groups: only selected groups apply according to configuration.
- Validation fails: service is not called and there are no side effects.

You can use Mockito verify to confirm `bookQueryService.search(...)` is not called in the validation failure case. This proves validation happens before the business method executes.

## 14. Common errors when using `@Arguments`

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| DTO receives all nulls | Top-level argument names do not match properties or constructor parameters | Compare SDL, DTO, and name resolver configuration |
| DTO only receives a single argument | Used `@Argument` instead of `@Arguments` | Use `@Arguments` when the full argument map of the field is needed |
| Unable to bind nested object | Child DTO lacks matching constructor/setter or type mismatch | Check constructor, setters, and nested types |
| `@Valid` does not run | Missing Validator bean or missing validation provider | Add the starter and check `LocalValidatorFactoryBean` |
| Constraints on child object do not run | Missing `@Valid` cascade on child property or collection element | Place `@Valid` in the right place |
| `@NotBlank` does not catch whitespace strings | Constraint not attached to bound DTO or validator not active | Check binding and validation provider |
| `@Arguments Map` does not trigger constraints | Raw map has no bean property constraints | Bind to a typed DTO or validate manually |
| BindException confused with validation exception | Binding and Bean Validation are two distinct stages | Handle binding errors and constraint errors separately |
| Validation group skips default constraints | Selected group does not include `Default` | Have the group extend `Default` or configure a group sequence |
| Client receives hard-to-read technical errors | GraphQL exception response not standardized | Use `@GraphQlExceptionHandler` or `@ControllerAdvice` |
| Service still runs despite invalid input | Missing `@Valid`/`@Validated` or validator not detected | Test method invocation and validator configuration |

## 15. Checklist for implementing validation on `@Arguments`

- [ ] Use `@Arguments` when binding all top-level arguments of a field.
- [ ] Use `@Argument` when needing only one specific argument or a named input object.
- [ ] Use a typed DTO instead of a raw map when automatic Bean Validation is needed.
- [ ] GraphQL argument names match DTO properties or constructor parameters.
- [ ] A Bean Validation provider and Validator bean are present.
- [ ] Place `@Valid` or `@Validated` on the `@Arguments` parameter.
- [ ] Place cascade `@Valid` on child objects and collection elements when needed.
- [ ] Use wrapper types when representing null values is necessary.
- [ ] Use class-level constraints for rules depending on multiple arguments.
- [ ] Distinguish GraphQL validation, binding, Bean Validation, and business validation.
- [ ] Handle `BindException` and validation exceptions as appropriate GraphQL errors.
- [ ] Do not return internal details in validation errors.
- [ ] Test valid inputs, invalid inputs, nested objects, and side effects using `GraphQlTester`.

## Conclusion

`@Arguments` is used to bind all arguments of the current GraphQL field into a single Java object. Unlike `@Argument`, which extracts a single named argument, `@Arguments` maps top-level arguments into properties of a DTO. It is a fitting choice when a resolver has multiple filters or search parameters that should be grouped into a typed structure.

To make automatic validation work, place `@Valid` or `@Validated` on the `@Arguments` parameter, ensure the application has a Bean Validation provider, and declare constraints on the DTO. For nested objects, cascade with `@Valid`; for rules involving multiple properties, use class-level constraints. Distinguish GraphQL schema errors, binding errors, and Bean Validation errors to handle each properly, then test with `GraphQlTester` to ensure resolvers do not execute business logic when arguments are invalid.

## References

- [Spring for GraphQL — Annotated Controllers: `@Arguments` and Validation](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — `Arguments` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/method/annotation/Arguments.html)
- [Spring for GraphQL — `GraphQlArgumentBinder` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/GraphQlArgumentBinder.html)
- [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/)
