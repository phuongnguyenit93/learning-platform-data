# BindException errors

In Spring for GraphQL, argument data from a GraphQL operation must be converted into the Java types required by the controller. This process normally happens automatically via **GraphQlArgumentBinder**. When data has passed GraphQL's checks but cannot be bound into a Java object via constructor or property binding, Spring can throw a **BindException**.

To handle this error properly, distinguish two stages: GraphQL validates and coerces data against the SDL; then Spring binds the processed values into Java parameters. This lesson focuses on the causes of BindException, how to read binding errors, designing suitable DTOs, translating errors into GraphQL errors, and testing argument binding.

## 1. What is BindException?

When a controller declares `@Argument`, Spring for GraphQL retrieves the corresponding argument from the GraphQL execution environment and converts it to the parameter's Java type.

Example schema:

~~~graphql
input BookSearchInput {
    keyword: String
    page: Int
    size: Int
}

type Query {
    searchBooks(input: BookSearchInput): [Book!]!
}
~~~

Controller:

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> searchBooks(
            @Argument("input") BookSearchInput input) {
        return bookService.search(input);
    }
}
~~~

Spring needs to convert the `input` value map into a `BookSearchInput` instance. Spring for GraphQL uses `GraphQlArgumentBinder` to perform this binding, including nested objects, collections, arrays, and maps.

If the binder cannot construct the target object or cannot assign one or more values to Java properties, binding errors are aggregated and reported as Spring Validation's `BindException`.

For instance, a DTO declares a constructor requiring primitive `int page`, while the schema allows `page` to be omitted or null. The binder cannot pass null into a primitive parameter. This is a compatibility mismatch between the bound data and the target Java type.

## 2. Distinguishing GraphQL input errors and BindException

Not every argument error is a BindException. GraphQL and Spring check data at different stages.

| Stage | Handling component | Example error |
| --- | --- | --- |
| Parse operation | GraphQL parser | Missing parenthesis or query syntax error. |
| Validate operation | GraphQL validator | Non-existent field, undeclared argument, or invalid selection set. |
| Coerce input | GraphQL engine | Missing non-null input field, invalid enum value, or wrong scalar type. |
| Bind to Java | GraphQlArgumentBinder | Unable to instantiate DTO, incompatible constructor, or unbindable property. |
| Business validation | Controller/service/Bean Validation | Page size exceeds limit, blank string, or invalid state transition. |
| Data execution | Service/repository | Resource not found or database error. |

For example, if the SDL declares:

~~~graphql
input BookFilterInput {
    page: Int!
}
~~~

The client sends:

~~~json
{
    "input": {}
}
~~~

In an operation calling `searchBooks(input: $input)`, the `$input` variable receives the empty object above.

GraphQL detects the missing required field before calling the resolver. This is an input coercion error; the controller method has not been called and it is not a BindException caused by the DTO.

Conversely, if the SDL allows a nullable field:

~~~graphql
input BookFilterInput {
    page: Int
}
~~~

but the Java DTO declares `int page`, the request passes SDL validation and then fails when Spring tries to bind null to the primitive. That scenario can lead to BindException.

Distinguishing the error stage helps choose the right fix: fix the operation/schema when GraphQL rejects the data, fix the DTO when binding fails, or fix the service when data is structurally valid but violates business rules.

## 3. How does GraphQlArgumentBinder perform binding?

GraphQlArgumentBinder takes argument values already processed by GraphQL and converts them into Java objects matching the target types declared by the controller method.

The binding process typically involves:

1. Retrieving the argument map of the field being executed.
2. Determining the target Java type from the method parameter or property being bound.
3. If the target type is an object, recursively processing its child properties.
4. Instantiating the object via a matching constructor or default constructor.
5. For mutable types, assigning values via property accessors/setters.
6. Collecting any binding errors that occur.
7. If errors exist, throwing a BindException containing a BindingResult; otherwise, returning the bound object.

The binder supports structures such as:

- Java classes or records.
- Nested objects.
- Lists, collections, and arrays.
- Maps.
- Data types convertible via the configured conversion mechanism.

Example nested input:

~~~graphql
input AuthorFilterInput {
    name: String
    country: String
}

input BookSearchInput {
    keyword: String
    author: AuthorFilterInput
    tags: [String!]
}
~~~

Corresponding Java DTOs:

~~~java
public record AuthorFilterInput(
        String name,
        String country
) {
}

public record BookSearchInput(
        String keyword,
        AuthorFilterInput author,
        List<String> tags
) {
}
~~~

Resolver:

~~~java
@QueryMapping
public List<Book> searchBooks(
        @Argument("input") BookSearchInput input) {
    return bookService.search(input);
}
~~~

The binder walks from `BookSearchInput` into `author`, then binds `name` and `country` onto `AuthorFilterInput`. If a child object cannot be instantiated or a value cannot be assigned, the error is recorded at the corresponding field path.

## 4. Common cause: primitive receiving null

Java primitives such as `int`, `long`, and `boolean` cannot hold null. Meanwhile, nullable GraphQL input fields can be omitted or explicitly passed as null.

Schema:

~~~graphql
input BookSearchInput {
    page: Int
    includeArchived: Boolean
}

type Query {
    searchBooks(input: BookSearchInput): [Book!]!
}
~~~

Error-prone DTO:

~~~java
public record BookSearchInput(
        int page,
        boolean includeArchived
) {
}
~~~

The client can send an empty object:

~~~json
{}
~~~

Both `page` and `includeArchived` can lack values. The binder cannot pass null to the constructor's two primitive parameters.

The right fix is using wrapper types:

~~~java
public record BookSearchInput(
        Integer page,
        Boolean includeArchived
) {
}
~~~

Then apply defaults in the service:

~~~java
public List<Book> search(BookSearchInput input) {
    int page = input.page() == null ? 0 : input.page();
    boolean includeArchived =
            Boolean.TRUE.equals(input.includeArchived());

    return bookRepository.search(page, includeArchived);
}
~~~

If a field is truly required, declare it non-null in the SDL and still consider wrapper types to represent input data clearly. GraphQL will reject missing/null values before the resolver runs.

Guidelines:

- Use `Integer` instead of `int` when a field may be missing or null.
- Use `Long` instead of `long` if the value can be null.
- Use `Boolean` instead of `boolean` when representing an unsupplied state.
- Only use primitives when the input contract guarantees a value is always present and the binding mechanism supports it.

## 5. Incompatible DTO constructor

The binder needs a way to instantiate Java objects. For immutable classes or records, the constructor must align with the input properties. For mutable classes, a default constructor and setters/property accessors can be used.

Example DTO:

~~~java
public class BookFilterInput {

    private String keyword;
    private Integer page;

    public BookFilterInput(String keyword) {
        this.keyword = keyword;
    }

    public String getKeyword() {
        return keyword;
    }

}
~~~

This class has a constructor accepting only `keyword`, no default constructor, and the `page` property has no setter. Because the constructor does not accept `page`, the binder has no way to write the remaining `page` value into the object; this DTO structure can cause binding errors. Either let the constructor accept all fields or provide property accessors capable of setting those values.

A straightforward design is using a record:

~~~java
public record BookFilterInput(
        String keyword,
        Integer page
) {
}
~~~

Or using a mutable class with a default constructor and setters:

~~~java
public class BookFilterInput {

    private String keyword;
    private Integer page;

    public BookFilterInput() {
    }

    public String getKeyword() {
        return keyword;
    }

    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }

    public Integer getPage() {
        return page;
    }

    public void setPage(Integer page) {
        this.page = page;
    }
}
~~~

When using complex classes, verify:

- Whether the constructor can be used by the binder.
- Whether constructor parameter names and types match the input fields.
- Whether mutable classes have a suitable default constructor and setters/property accessors.
- Whether all fields to bind are reachable via property accessors.
- Whether nested DTOs follow the same instantiation rules as the root DTO.

Do not add constructors solely to appease the binder without considering data semantics. Choose a DTO model that is clear, easy to test, and aligned with the SDL structure.

## 6. Java type does not match SDL type

The SDL is the data type contract visible to clients. Java DTOs need target types compatible with GraphQL values after coercion.

Example:

~~~graphql
input PriceRangeInput {
    minPrice: Float
    maxPrice: Float
}
~~~

DTO:

~~~java
public record PriceRangeInput(
        BigDecimal minPrice,
        BigDecimal maxPrice
) {
}
~~~

Binding requires an appropriate conversion for the numeric type supplied by GraphQL. If the application uses an incompatible Java type or custom scalar, the binder may fail to convert the value.

Things to check:

- GraphQL `Int` is typically represented by a compatible integer type; the Java field should not require a type incapable of accepting that value.
- GraphQL `Float` carries floating-point semantics; choose consistent Java types and conversions.
- GraphQL `ID` can accept strings or integers per GraphQL rules; DTOs typically use `String` when IDs are treated as identifiers.
- Java enums must match enum values published by the schema or have a configured conversion mapping.
- Custom scalars must have coercing and conversions compatible with the target Java type.

Do not change the SDL to `String` just to avoid number or date/time binding errors. Keep GraphQL types aligned with the true API contract and configure Java/custom scalars accordingly.

## 7. Errors in nested objects and collections

BindException can originate from a field deep inside an input object.

Schema:

~~~graphql
input AddressInput {
    city: String
    postalCode: String
}

input AuthorInput {
    name: String
    address: AddressInput
}

input BookSearchInput {
    author: AuthorInput
}
~~~

DTO:

~~~java
public record AddressInput(
        String city,
        Integer postalCode
) {
}

public record AuthorInput(
        String name,
        AddressInput address
) {
}

public record BookSearchInput(
        AuthorInput author
) {
}
~~~

Here `postalCode` is declared `String` in the SDL while Java uses `Integer`. If the client sends a postal code containing letters, conversion can fail. Even when numeric, postal code identifiers should usually use `String` to preserve leading zeros and formatting characters.

A more suitable example:

~~~java
public record AddressInput(
        String city,
        String postalCode
) {
}
~~~

For collections, ensure the Java element type matches:

~~~graphql
input BookSearchInput {
    tags: [String!]
}
~~~

~~~java
public record BookSearchInput(List<String> tags) {
}
~~~

If an element cannot be converted to its corresponding Java type or a nested object inside a list cannot be instantiated, binding can fail. When errors occur inside nested structures, inspect the field path in `BindingResult` to pinpoint the exact element or property causing the failure.

## 8. Reading BindException and BindingResult

Spring Validation's `BindException` contains a `BindingResult`, which holds the list of errors by object and field.

You can read the field errors:

~~~java
import org.springframework.validation.BindException;
import org.springframework.validation.FieldError;

public void logBindingErrors(BindException exception) {
    for (FieldError error :
            exception.getBindingResult().getFieldErrors()) {

        log.warn(
                "Argument binding failed at field {}: {}",
                error.getField(),
                error.getDefaultMessage()
        );
    }
}
~~~

Useful fields:

| Information | Meaning |
| --- | --- |
| `getObjectName()` | Name of the object being bound. |
| `getField()` | Field path that caused the error. |
| `getDefaultMessage()` | Error description suitable for developers. |
| `getCode()` | Binding/validation error code. |
| `getRejectedValue()` | Rejected value; handle with care when logging. |

For example, a field path might indicate `author.address.postalCode`, pinpointing that the error lies inside a nested object rather than the entire argument.

Do not log full rejected values to production logs if the data could contain passwords, tokens, personal information, or sensitive data. Log only the field path, error code, and correlation ID whenever possible.

Likewise, never forward raw `getDefaultMessage()` or rejected values directly to clients without inspection. Binding messages can sometimes expose Java type details, property names, or internal data.

## 9. Translating BindException into a GraphQL error

Errors occurring during data fetcher invocation can be handled using Spring for GraphQL's exception resolution mechanism.

You can use `@GraphQlExceptionHandler` inside `@ControllerAdvice` to standardize responses:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.validation.BindException;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlErrorHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleBindException(BindException exception) {
        return GraphqlErrorBuilder.newError()
                .message("Argument data does not match the expected input type.")
                .errorType(ErrorType.BAD_REQUEST)
                .build();
    }
}
~~~

The handler returns a generic message to the client. Technical details can be logged on the server so developers can investigate the root cause.

If you need to return a list of failing fields to the client, build a controlled `extensions` structure containing only field names and stable error codes. Do not include rejected values or internal details in the response.

Another strategy is implementing `DataFetcherExceptionResolver` when handling errors application-wide, mapping multiple exception types into a unified GraphQL error convention. Pick one consistent handling mechanism to avoid converting the same exception in multiple places with inconsistent payloads.

Note: GraphQL parse, validation, or input coercion errors can occur before any data fetcher runs. `@GraphQlExceptionHandler` handles exceptions thrown during resolver execution; it does not replace all GraphQL request error handling.

## 10. Distinguishing BindException from Bean Validation

BindException and Bean Validation solve two different problems.

- **Binding** converts input data into Java objects.
- **Validation** checks whether a properly structured object satisfies constraints.

Example DTO:

~~~java
public record CreateBookInput(
        String title,
        Integer pageCount
) {
}
~~~

An object can bind successfully yet remain invalid according to business rules: blank title or negative pageCount.

You can use Jakarta Bean Validation:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        @Min(1) @Max(5000) Integer pageCount
) {
}
~~~

For constraints to run, the application needs the validation dependency and configuration, and validation must be triggered at the argument-receiving point in the manner supported by your Spring for GraphQL version. Without triggering validation, merely placing annotations on a DTO does not guarantee constraints execute automatically.

With partial inputs, note that omitted fields and null fields carry distinct meanings. Constraints like `@NotBlank` handle null per the constraint's own rules, but do not express "leave unchanged" or "clear value". Combine validation with `ArgumentValue<T>` or business logic when presence states must be distinguished.

## 11. Fixing DTOs to prevent BindException

When encountering an error, do not blindly change Java types across the board. Check the exact field path and fix the root cause.

Some principles:

**Use wrappers for nullable fields.** If the SDL allows omission or null, prefer `Integer`, `Long`, `Boolean` over their corresponding primitives.

**Keep nested object structures consistent.** If the SDL has `AuthorInput` containing `AddressInput`, DTOs should reflect that exact relationship.

**Choose an appropriate constructor.** Records suit immutable DTOs; mutable classes require a default constructor and appropriate setters/property accessors if using property binding.

**Choose semantically accurate Java types.** Postal codes, phone numbers, and IDs should usually be `String` even if they contain digits. Quantities and numeric calculations should use numeric types.

**Configure conversions when needed.** For custom scalars or domain-specific types, provide proper conversions/coercing instead of casting manually in every resolver.

**Do not use persistence entities as input DTOs.** Create dedicated input classes to control which fields clients may send and avoid accidentally binding internal properties.

Example of a well-designed DTO:

~~~graphql
input BookSearchInput {
    keyword: String
    page: Int
    size: Int
    author: AuthorFilterInput
}

input AuthorFilterInput {
    name: String
    countryCode: String
}
~~~

~~~java
public record AuthorFilterInput(
        String name,
        String countryCode
) {
}

public record BookSearchInput(
        String keyword,
        Integer page,
        Integer size,
        AuthorFilterInput author
) {
}
~~~

Wrapper Java types align with nullable fields. The service is responsible for choosing defaults and enforcing `page`/`size` bounds.

## 12. Testing binding errors with GraphQlTester

Test both successful binding and cases that trigger BindException.

Example schema:

~~~graphql
input BookSearchInput {
    page: Int
}

type Query {
    searchBooks(input: BookSearchInput!): [Book!]!
}
~~~

Faulty DTO using a primitive:

~~~java
public record BookSearchInput(int page) {
}
~~~

Resolver:

~~~java
@QueryMapping
public List<Book> searchBooks(
        @Argument("input") BookSearchInput input) {
    return bookService.search(input);
}
~~~

Test sending an object without `page`:

~~~java
@Test
void reportsBindingErrorWhenNullablePageCannotBindToPrimitive() {
    graphQlTester.document("""
            query SearchBooks($input: BookSearchInput!) {
                searchBooks(input: $input) {
                    id
                }
            }
            """)
        .variable("input", Map.of())
        .execute()
        .errors()
        .satisfy(errors -> assertThat(errors).isNotEmpty());
}
~~~

After switching the DTO to a wrapper:

~~~java
public record BookSearchInput(Integer page) {
}
~~~

you can test that an empty object binds successfully and the service applies the appropriate default.

Cases to include in the test suite:

- Valid input object with all fields.
- Omitted nullable field.
- Nullable field sent as null.
- Primitive receiving an omitted nullable field.
- Nested DTO containing an unbindable field.
- Collection containing an incompatible element.
- GraphQL rejecting invalid enums or scalars before the resolver runs.
- BindException translated into a GraphQL error per convention.
- Bean Validation rejecting bound data that fails constraints.
- Response not leaking rejected values or internal details.

For error tests, do not only assert that `errors` is non-empty. Verify the error type or error code published by your application, and confirm the service is not invoked when binding fails.

## 13. Common errors and fixes

| Symptom | Common cause | Fix |
| --- | --- | --- |
| BindException when field is omitted | Java primitive cannot accept null. | Switch to a wrapper such as `Integer` or `Boolean`. |
| Unable to instantiate DTO | Missing suitable constructor or missing required default constructor/property accessors. | Use an appropriate record or mutable class with constructors/setters. |
| Error in nested field | Child DTO is incompatible with nested input object. | Align structures and types at every level. |
| Unable to convert value | Target Java type or conversion is incompatible. | Use semantically matching Java types or configure converters/custom scalars. |
| Unknown input field | Client sent a field not present in SDL. | Fix the operation; this is usually a GraphQL validation error prior to binding. |
| Missing non-null input field | Client omitted a required field. | Supply the field; this is a GraphQL input coercion error. |
| Invalid enum value | Value is not declared in schema enum. | Use a valid enum value; GraphQL rejects it before the binder runs. |
| DTO binds but data violates business rules | Missing validation after binding. | Add Bean Validation or validate in the service. |
| Client receives overly detailed errors | Returning raw BindException details. | Standardize GraphQL errors and log details safely on the server. |

## 14. Workflow for diagnosing BindException

When you see BindException in logs or GraphQL responses, check in order:

1. Identify the GraphQL field and resolver receiving the argument.
2. Read the object name, field path, and default message in `BindingResult`.
3. Compare the field path against the input type in the SDL.
4. Check target Java types, especially primitives, wrappers, and nested DTOs.
5. Check constructors, setters, and property accessors on the class.
6. Determine whether the value was omitted, explicit null, or a concrete value.
7. Check custom scalars or conversions for domain-specific types.
8. Distinguish binding from Bean Validation and business validation.
9. Verify whether the exception resolver standardizes errors properly.
10. Write a minimal reproduction test using `GraphQlTester` before modifying the DTO or schema.

Diagnostic diagram:

~~~mermaid
flowchart TD
    A["GraphQL receives argument"] --> B["Parse, validate, and coerce per SDL"]
    B --> C{"Input valid per schema?"}
    C -->|No| D["GraphQL request/input error"]
    C -->|Yes| E["GraphQlArgumentBinder"]
    E --> F{"Can bind Java object?"}
    F -->|No| G["BindException"]
    F -->|Yes| H["Bean/business validation"]
    H --> I{"Data valid?"}
    I -->|No| J["Validation error"]
    I -->|Yes| K["Call service"]
    G --> L["Exception resolver / GraphQL error"]
    J --> L
    K --> M["Return result"]
~~~

Fixing errors by their exact field path is usually faster and safer than rewriting the whole DTO. If multiple fields fail together, inspect constructor design and Java types first.

## 15. Key takeaways

- `BindException` occurs when Spring cannot bind GraphQL-processed argument values into the target Java type.
- `GraphQlArgumentBinder` supports recursive binding for nested objects, collections, arrays, and maps.
- GraphQL parsing, validation, and input coercion occur before Java object binding.
- Nullable fields can be omitted or receive null; Java primitives cannot represent those states.
- Use wrapper types for nullable data and design matching constructors/property accessors.
- `BindingResult` provides the object name, field path, and specific errors for diagnostics.
- Binding errors differ from Bean Validation and business validation.
- You can standardize `BindException` into GraphQL errors using `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver`.
- Never send rejected values or internal details to clients.
- Use `GraphQlTester` to test successful binding, failed binding, and exception handler behavior.

BindException usually indicates a mismatch between GraphQL data and the Java model expected by the resolver. By properly distinguishing coercion, binding, and validation errors—and designing DTOs to match SDL nullability and structure—Spring for GraphQL applications handle arguments reliably and remain easy to diagnose.
