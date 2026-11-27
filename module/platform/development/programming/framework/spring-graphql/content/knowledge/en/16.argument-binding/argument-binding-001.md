# @Argument

A GraphQL field can accept arguments so that clients can pass identifiers, filter criteria, sorting options, or input data for an operation. In Spring for GraphQL, the **@Argument** annotation retrieves an argument from the GraphQL execution context and binds its value to a controller method parameter. As a result, the resolver works directly with Java types such as String, enum, record, or DTO instead of manually reading and casting data from the request.

@Argument is part of the annotated controller mechanism. It is commonly used alongside @QueryMapping, @MutationMapping, or @SchemaMapping. To use it effectively, you need to understand how the argument name is determined, at which step GraphQL converts types, how Spring binds input objects into Java, and how to handle cases where the client omits an argument or passes null.

## What does @Argument do?

Suppose a schema has a field that fetches a book by ID:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

The client calls the book field and passes the id argument:

~~~graphql
query FindBook {
  book(id: "book-101") {
    id
    title
  }
}
~~~

In Spring for GraphQL, the resolver receives that value using @Argument:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String bookId) {
        return bookService.findById(bookId);
    }
}
~~~

When GraphQL executes the book field, Spring retrieves the argument value named id, converts it to the appropriate Java type, and passes it into the bookId parameter. The Java variable name can differ from the argument name in the schema because the annotation explicitly specifies the name to bind.

@Argument does not parse the entire GraphQL query, nor does it access the database directly. GraphQL Java is responsible for parsing and validating the operation; Spring for GraphQL provides the mechanism to bind arguments to Java parameters; the service executes business logic and accesses data.

## How is the argument name determined?

There are two common ways to declare it:

~~~java
@QueryMapping
public Book book(@Argument("id") String bookId) {
    return bookService.findById(bookId);
}
~~~

Explicitly declaring the name in the annotation is suitable when the argument name in the SDL differs from the Java parameter name. If both names are the same, you can omit the name:

~~~java
@QueryMapping
public Book book(@Argument String id) {
    return bookService.findById(id);
}
~~~

When the name is omitted, Spring relies on the Java parameter name to find the corresponding argument. For this mechanism to work reliably, the application must retain parameter name metadata during Java compilation, typically using the **-parameters** compiler option. If the metadata is absent, Spring may not be able to infer the parameter name and binding will fail.

For important APIs or when the Java name differs from the schema name, explicitly specifying the name like @Argument("id") makes the mapping easier to read and avoids depending on compiler configuration.

## Through what steps is an argument value converted?

The binding process can be visualized by the following flow:

~~~mermaid
flowchart TD
    A["GraphQL document and variables"] --> B["GraphQL parse and validation"]
    B --> C["GraphQL scalar / enum coercion"]
    C --> D["Argument map in DataFetchingEnvironment"]
    D --> E["@Argument in annotated controller"]
    E --> F["GraphQlArgumentBinder"]
    F --> G["Java parameter"]
    G --> H["Controller calls service"]
~~~

GraphQL validates types against the SDL and performs coercion for scalars, enums, or custom scalars before invoking the resolver. Spring for GraphQL then binds the argument values to the Java parameter types. For input objects, the binder can convert nested maps into the corresponding record or DTO.

This means GraphQL type errors and Java binding errors are two distinct kinds of issues:

- If a client passes a string to an Int argument, GraphQL can reject the operation at the coercion step before the resolver runs.
- If the input object is valid according to GraphQL but cannot construct the target Java object, the error occurs at the argument binding step.
- If binding succeeds but the value violates business rules, the service or validation layer needs to handle it.

## Binding scalars and enums

GraphQL scalars are typically bound to corresponding Java types:

| GraphQL type | Common Java type | Example |
| --- | --- | --- |
| ID | String | Book ID |
| String | String | Keyword |
| Int | Integer or int if guaranteed non-null | Quantity |
| Float | Double | Floating-point value |
| Boolean | Boolean or boolean if guaranteed non-null | Toggle flag |
| Custom scalar Date | LocalDate if scalar coercion returns LocalDate | Publication date |

For nullable arguments, you should use wrapper types such as Integer or Boolean because primitive types int and boolean cannot represent null. For non-null arguments, GraphQL already checks the required value before invoking the resolver, though wrapper types are still useful when you want consistent Java signatures.

An enum in the SDL can be bound to a Java enum with matching constant names:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Query {
  books(status: BookStatus): [Book!]!
}
~~~

~~~java
public enum BookStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}

@QueryMapping
public List<Book> books(@Argument("status") BookStatus status) {
    return bookService.findByStatus(status);
}
~~~

The enum value sent by the client must belong to the set of values declared in the schema. Do not use String for an enum just for flexibility; enum types give better compiler and IDE support while preventing invalid status strings.

## Binding custom scalars

Custom scalars are coerced by GraphQL Java before Spring binds the argument. Therefore, the Java parameter type must be compatible with the type returned by the scalar from parseValue or parseLiteral.

For example, suppose a Date scalar is configured to parse into java.time.LocalDate:

~~~graphql
scalar Date

type Query {
  books(publishedAfter: Date): [Book!]!
}
~~~

The resolver can accept LocalDate:

~~~java
@QueryMapping
public List<Book> books(@Argument("publishedAfter") LocalDate publishedAfter) {
    return bookService.findPublishedAfter(publishedAfter);
}
~~~

If the Date scalar is configured to return a String while the method expects LocalDate, binding requires an appropriate converter or a conversion error will occur. Keep the coercion contract and the Java type consistent to avoid repeated conversions across multiple layers.

## Binding input objects into Java records

When a field accepts multiple related pieces of data, the schema typically groups them into an input object:

~~~graphql
input BookFilterInput {
  keyword: String
  authorId: ID
  status: BookStatus
  publishedAfter: Date
}

type Query {
  searchBooks(filter: BookFilterInput): [Book!]!
}
~~~

You can represent the input object with a Java record:

~~~java
public record BookFilter(
        String keyword,
        String authorId,
        BookStatus status,
        LocalDate publishedAfter) {
}
~~~

The resolver receives the entire input object:

~~~java
@QueryMapping
public List<Book> searchBooks(@Argument("filter") BookFilter filter) {
    return bookService.search(filter);
}
~~~

Spring for GraphQL uses **GraphQlArgumentBinder** to convert input data into the target object. The binder supports constructor binding and property binding, and handles nested structures. For a record, the record components are bound via the constructor; component names should correspond to the field names in the input object.

If the filter argument can be omitted or passed as null, the BookFilter parameter can receive null. If you want the filter object itself to be required, declare filter: BookFilterInput! in the SDL. Distinguish between whether the object must be present and whether each field inside the object is required.

## Binding input objects into POJOs

Using a record is not mandatory. You can use a standard Java class:

~~~java
public class BookFilter {

    private String keyword;
    private String authorId;
    private BookStatus status;

    public BookFilter() {
    }

    public String getKeyword() {
        return keyword;
    }

    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }

    public String getAuthorId() {
        return authorId;
    }

    public void setAuthorId(String authorId) {
        this.authorId = authorId;
    }

    public BookStatus getStatus() {
        return status;
    }

    public void setStatus(BookStatus status) {
        this.status = status;
    }
}
~~~

For a POJO with an appropriate constructor and setters, the binder can instantiate the object and assign the corresponding properties. Constructor binding fits immutable types such as records; property binding is useful for JavaBeans with setters. Choose a consistent data style in your project so binding and validation remain predictable.

## Renaming input fields with @BindParam

GraphQL field names typically use camelCase, but Java may use different conventions or names. Spring for GraphQL provides **@BindParam** to specify the input field name to bind to a constructor parameter or property.

For example, if the schema uses snake_case:

~~~graphql
input BookFilterInput {
  author_id: ID
  published_after: Date
}
~~~

And the Java record uses camelCase:

~~~java
import org.springframework.graphql.data.method.annotation.BindParam;

public record BookFilter(
        @BindParam("author_id") String authorId,
        @BindParam("published_after") LocalDate publishedAfter) {
}
~~~

@BindParam helps decouple public GraphQL field names from Java property names. If the schema and Java already use the same names, there is no need to add this annotation. Avoid arbitrary renaming because input field names are part of the contract clients rely on.

## Binding nested input objects and lists

A GraphQL input object can contain other objects or lists. The Java model should reflect the same structure:

~~~graphql
input AuthorFilterInput {
  name: String
}

input BookFilterInput {
  keyword: String
  author: AuthorFilterInput
  statuses: [BookStatus!]
}

type Query {
  searchBooks(filter: BookFilterInput): [Book!]!
}
~~~

~~~java
public record AuthorFilter(String name) {
}

public record BookFilter(
        String keyword,
        AuthorFilter author,
        List<BookStatus> statuses) {
}
~~~

~~~java
@QueryMapping
public List<Book> searchBooks(@Argument BookFilter filter) {
    return bookService.search(filter);
}
~~~

The binder traverses the input map structure to create the corresponding nested objects and lists. Generic types should be fully declared, such as List<BookStatus>, so Spring has enough type information to convert elements.

If a nested object or a list element fails to bind, an error can occur even if the remaining fields are valid. Validate inputs at each level and return clear validation messages.

## Distinguishing omitted arguments from null with ArgumentValue

For a nullable argument, a regular Java parameter receives null in both cases: the client did not send the argument, or the client sent the argument with a null value. In some business scenarios, these two cases have different meanings.

For example, with a status filter:

- Omitting status means not filtering by status.
- Passing status: null may mean finding records that have no status yet.
- Passing status: PUBLISHED means fetching only published records.

Spring for GraphQL provides **ArgumentValue<T>** to preserve whether the argument was omitted:

~~~java
import org.springframework.graphql.data.ArgumentValue;
import org.springframework.graphql.data.method.annotation.Argument;

@QueryMapping
public List<Book> books(
        @Argument("status") ArgumentValue<BookStatus> status) {

    if (status.isOmitted()) {
        return bookService.findWithoutStatusFilter();
    }

    if (status.value() == null) {
        return bookService.findBooksWithNullStatus();
    }

    return bookService.findByStatus(status.value());
}
~~~

ArgumentValue is useful when the resolver needs to distinguish between omitted and explicit null. If the schema declares a default value, GraphQL may apply the default before calling the resolver; clearly define the default contract and test the actual behavior of that argument.

## Using @Argument in @SchemaMapping

Arguments do not only appear on root Query or Mutation fields. Fields on object types can also accept arguments. For example, a client requests the maximum number of reviews for a book:

~~~graphql
type Book {
  id: ID!
  title: String!
  reviews(first: Int = 10): [Review!]!
}
~~~

The resolver receives both the source object and the argument:

~~~java
@Controller
public class BookFieldController {

    private final ReviewService reviewService;

    public BookFieldController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @SchemaMapping(typeName = "Book", field = "reviews")
    public List<Review> reviews(
            Book book,
            @Argument("first") Integer first) {
        return reviewService.findByBookId(book.id(), first);
    }
}
~~~

The Book parameter is the source object that GraphQL is resolving; the parameter annotated with @Argument retrieves the first value of the reviews field. When a method receives multiple kinds of inputs, the annotation helps Spring distinguish arguments from the source object and other special parameters.

## Accepting a Map when a flexible structure is needed

If you do not want to create a DTO for a simple input object or a truly dynamic structure, you can bind the argument as a Map:

~~~java
@QueryMapping
public List<Book> searchBooks(
        @Argument("filter") Map<String, Object> filter) {
    return bookService.search(filter);
}
~~~

A Map provides dynamic key access but loses many benefits of static typing. The code must manually check key existence, value types, and nested structures. For a stable schema, a record or DTO is generally safer and easier to maintain.

Do not accept the entire input as a Map just to avoid designing a model. An explicit Java type allows the compiler to catch misspelled field names, enables IDE refactoring support, and lets validation annotations be attached directly to properties.

## Binding errors and how to handle them

The Spring GraphQL argument binder can detect errors when it cannot convert or construct the target object. Common errors include:

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Parameter receives null | @Argument name does not match argument name in SDL | Check the name and declare it explicitly |
| Parameter name cannot be found | Missing parameter name metadata when omitting name in @Argument | Use an explicit name or enable -parameters |
| Unable to instantiate record | Constructor names/order/components do not match data | Compare input fields against record components |
| Nested field fails to bind | Java type does not reflect input structure | Check nested DTOs and generic types |
| Wrong scalar type | GraphQL input does not match scalar or converter is incompatible | Check SDL, custom scalar coercion, and Java target type |
| Invalid enum | Submitted value is not in schema enum | Use the exact published enum value |
| Omitted and null treated identically | Parameter is just a regular nullable type | Use ArgumentValue when distinction is needed |

GraphQL coercion errors typically occur before the resolver is invoked. Java binding errors occur when GraphQL has obtained the argument value but Spring cannot convert it to the target type. Business errors occur after binding succeeds and must be handled in the service or validation layer.

Do not catch all binding errors and silently replace them with an empty object. Doing so could cause the resolver to execute queries with unintended default conditions. Return appropriate errors and keep diagnostic details in server logs without exposing sensitive data to the client.

## Validation after binding

Successful binding only proves that the data can be converted into Java types. It does not prove that the data is valid according to business rules. For example, quantity can bind to an Integer while a negative value is still invalid; start and end years may both be integers while their relationship is invalid.

You can combine Jakarta Bean Validation with input DTOs:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record BookSearchInput(
        @NotBlank @Size(max = 100) String keyword,
        @Min(1) @Max(100) Integer size) {
}
~~~

~~~java
import jakarta.validation.Valid;

@MutationMapping
public Book createBook(@Argument @Valid CreateBookInput input) {
    return bookService.create(input);
}
~~~

Validation requires appropriate dependencies and configuration, such as the Spring Boot validation starter. Depending on the Spring GraphQL version and how method validation is configured, errors may be represented as validation exceptions or binding exceptions. Standardize them into GraphQL errors with clear messages that do not leak internal details.

Rules that depend on existing data—such as whether the user is permitted to modify a record, whether an author ID exists, or whether a tenant has access—should still be checked in the service or domain layer.

## Testing @Argument

Spring for GraphQL provides GraphQlTester to test argument binding through real operations:

~~~java
graphQlTester.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-101")
    .execute()
    .path("book.id")
    .entity(String.class)
    .isEqualTo("book-101");
~~~

For input objects, you can pass variables as a Map:

~~~java
graphQlTester.document("""
        query Search($filter: BookFilterInput) {
            searchBooks(filter: $filter) {
                id
                title
            }
        }
        """)
    .variable("filter", Map.of(
            "keyword", "Spring",
            "status", "PUBLISHED"))
    .execute()
    .path("searchBooks")
    .entityList(Book.class)
    .hasSize(2);
~~~

You should test:

- Valid scalar and enum arguments.
- Explicit argument names that differ from Java parameter names.
- Input objects bound to records or POJOs.
- Nested input objects and lists.
- Custom scalars converted to the expected Java type.
- Nullable arguments omitted or passed as null.
- Non-null arguments missing or passed as null.
- Values that bind successfully but violate business validation.
- Binding errors translated into appropriate GraphQL errors.

When you need to verify the full HTTP transport, you can use HttpGraphQlTester combined with WebTestClient. For service unit tests, test business logic independently of GraphQL binding.

## Guidelines for using @Argument

When writing annotated controllers, keep the following in mind:

1. **Keep names synchronized with SDL.** Use @Argument("name") when the Java name differs from the argument name or when you want explicit mapping.
2. **Choose appropriate Java types.** Use wrappers for nullable values, enums for enums, and records/DTOs for input objects.
3. **Keep input structures consistent.** Nested inputs and lists should have corresponding Java models.
4. **Understand GraphQL coercion before binding.** Custom scalars must return a Java type that the parameter can accept.
5. **Use @BindParam when renaming is needed.** Keep the public schema independent of Java property naming conventions.
6. **Use ArgumentValue at the right time.** Only needed when business logic distinguishes an omitted argument from an explicit null.
7. **Validate on the server.** Successful binding does not replace validation and authorization.
8. **Prefer static types.** Use Map for truly dynamic data, not to avoid modeling.
9. **Test via operations.** Verify successful binding, coercion errors, and validation errors.

@Argument is the bridge between arguments in a GraphQL schema and Java parameters in an annotated controller. GraphQL Java is responsible for parsing, validation, and coercion; Spring for GraphQL uses GraphQlArgumentBinder to construct Java values; the controller calls the service to process business logic. When names, data types, and input structures are designed consistently, resolvers become easier to read, easier to test, and less prone to conversion errors.
