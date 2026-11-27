# Method argument resolution

In Spring for GraphQL, a handler method can accept several kinds of parameters: arguments sent by the client, the source object from the parent field, data in the GraphQL context, or the execution environment. **Method argument resolution** is the mechanism Spring uses to resolve those values and pass them into the appropriate Java parameters when a `DataFetcher` invokes the handler.

Understanding this mechanism helps avoid confusing a field's arguments with the source object, bind input objects safely into records/DTOs, distinguish omitted fields from explicitly `null` fields, and share request data through context. It is the foundation for writing resolvers with **@QueryMapping**, **@MutationMapping**, and **@SchemaMapping** without working directly with `DataFetchingEnvironment` in every method.

This lesson explains how Spring selects and binds handler parameters, how to use **@Argument** and **@Arguments**, how to receive the source object, GraphQL context, `Principal`, and `DataFetchingEnvironment`, as well as validation, binding error handling, and testing.

## 1. What is method argument resolution?

GraphQL Java invokes a `DataFetcher` when it needs to resolve a field. For annotated controllers, Spring registers a `DataFetcher` as an adapter to invoke the Java method. Before calling the method, Spring must resolve the value for each parameter.

Example schema:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

Handler:

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

When the client sends a query with an ID, Spring:

1. Receives the `DataFetchingEnvironment` for the `Query.book` field.
2. Reads the argument named `id`.
3. Converts the value to the declared Java `String` type.
4. Calls the `book` method with the `bookId` parameter.
5. Converts the method's return value into the `DataFetcher` result.

Resolving the right value for each parameter is handled by the system of method argument resolvers. Each parameter kind is identified by its annotation or type, and then extracted from the GraphQL execution context.

## 2. Data sources that can be passed into a handler

A handler method can receive data from several different sources:

| Source | How to receive | When to use |
|---|---|---|
| Field argument | **@Argument** | Read a single value or input object sent by the client |
| All arguments | **@Arguments** | Bind multiple arguments into a `Map`/DTO |
| Source object | Parameter of the corresponding Java type | Resolve a child field of a parent object |
| GraphQL context | **@ContextValue** or `GraphQLContext` | Data shared across a single request |
| Local context | **@LocalContextValue** | Data passed along a specific field branch |
| Execution environment | **DataFetchingEnvironment** | Need low-level access to GraphQL execution details |
| Current user | **Principal** | Obtain the authenticated principal when integrated |

Not every method needs all sources. Declare only the parameters the handler actually uses so the method signature stays readable and easy to test.

## 3. Reading a single argument with `@Argument`

**@Argument** reads a specific argument of a GraphQL field and binds it to a Java parameter.

SDL:

~~~graphql
type Query {
  book(id: ID!, includeArchived: Boolean = false): Book
}
~~~

Handler:

~~~java
@QueryMapping
public Book book(
        @Argument("id") String bookId,
        @Argument("includeArchived") Boolean includeArchived) {

    return bookService.findById(bookId, includeArchived);
}
~~~

The name in **@Argument** is the argument name in the SDL. The Java variable name can differ from the GraphQL name:

- GraphQL argument: **id**
- Java parameter: **bookId**

If you omit the name in the annotation, Spring can infer the argument name from the Java parameter name. This inference relies on parameter name metadata being available in the bytecode. To avoid issues caused by compiler configuration or variable refactoring, you can declare the name explicitly.

~~~java
@QueryMapping
public Book book(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

### Java type must be compatible with the GraphQL type

GraphQL scalars are typically bound to corresponding Java types:

| GraphQL type | Common Java type |
|---|---|
| **ID** | `String` |
| **String** | `String` |
| **Int** | `Integer` |
| **Float** | `Double` |
| **Boolean** | `Boolean` |
| **Enum** | Matching Java enum |
| **[T]** | `List`/Collection/array of type `T` |
| **Input object** | Java record or DTO |

For custom scalars, the Java type depends on the scalar implementation and coercing configuration. Do not assume every custom scalar automatically binds to `String`.

GraphQL performs parsing and input coercion before calling the resolver. Thus, the handler usually receives values already coerced according to schema types, which Spring then binds to the target Java type.

## 4. Binding an input object into a record or DTO

When a mutation accepts multiple structured values, group them into an input object.

SDL:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  status: BookStatus = DRAFT
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Java record:

~~~java
public record CreateBookInput(
        String title,
        String authorId,
        BookStatus status) {
}
~~~

Handler:

~~~java
@MutationMapping
public Book createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
~~~

Spring for GraphQL uses **GraphQlArgumentBinder** to bind argument values into the target Java type. The binder supports constructor binding and property binding, including nested object structures, collections, and maps.

### Constructor binding

For Java records, the record's components are used to construct an instance:

~~~java
public record AddressInput(
        String street,
        String city,
        String postalCode) {
}

public record CreateBookInput(
        String title,
        String authorId,
        AddressInput shippingAddress) {
}
~~~

When variables have nested structures, Spring binds the child object into `AddressInput` and passes it into the `CreateBookInput` constructor.

### Property binding

For a JavaBean with a default constructor and setters, the binder can assign values to properties:

~~~java
public class BookFilter {

    private String titlePrefix;
    private BookStatus status;

    public String getTitlePrefix() {
        return titlePrefix;
    }

    public void setTitlePrefix(String titlePrefix) {
        this.titlePrefix = titlePrefix;
    }

    public BookStatus getStatus() {
        return status;
    }

    public void setStatus(BookStatus status) {
        this.status = status;
    }
}
~~~

Records are usually well suited for immutable, clearly structured input DTOs. JavaBeans can be useful when property binding is needed or for compatibility with existing data models. Whichever you use, only accept fields that are declared in the GraphQL input type and needed for the use case.

## 5. How does `GraphQlArgumentBinder` convert data?

After coercion, a GraphQL input object is typically represented as maps and collections. `GraphQlArgumentBinder` converts that structure into Java objects:

~~~text
GraphQL variables
      |
      v
GraphQL input coercion
      |
      v
Map / List / scalar values
      |
      v
GraphQlArgumentBinder
      |
      +--> Constructor binding
      |
      +--> Property binding
      |
      v
Java record / DTO / collection
      |
      v
Annotated handler method
~~~

The binder uses Spring's conversion service and binding mechanism to process data types. If a structure or value cannot be bound into the target Java type, binding can raise an error rather than silently creating an invalid object.

For example, the SDL declares:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
}
~~~

But the Java record declares:

~~~java
public record CreateBookInput(
        String title,
        Long authorId) {
}
~~~

An `ID` value may be coerced into a string; binding it to `Long` depends on available conversions and the ID format. If domain IDs are opaque strings, use `String` instead of forcing them into numbers just because a few sample IDs look numeric.

### Consistent field naming

Field names in an input object should match Java properties or constructor parameters. If the SDL uses camelCase, the Java record should also use camelCase:

~~~graphql
input BookFilterInput {
  titlePrefix: String
  minimumPageCount: Int
}
~~~

~~~java
public record BookFilterInput(
        String titlePrefix,
        Integer minimumPageCount) {
}
~~~

Mismatched names or incompatible types are common causes of argument binding failures.

## 6. Binding all arguments with `@Arguments`

If a field has several arguments and the handler needs the entire group, you can use **@Arguments**. Spring binds all arguments into a `Map` or a JavaBean/DTO.

SDL:

~~~graphql
type Query {
  searchBooks(
    titlePrefix: String
    status: BookStatus
    first: Int = 20
  ): [Book!]!
}
~~~

Receiving as a `Map`:

~~~java
@QueryMapping
public List<Book> searchBooks(@Arguments Map<String, Object> arguments) {
    String titlePrefix = (String) arguments.get("titlePrefix");
    BookStatus status = (BookStatus) arguments.get("status");
    Integer first = (Integer) arguments.get("first");

    return bookService.search(titlePrefix, status, first);
}
~~~

Receiving as a DTO:

~~~java
public record BookSearchArguments(
        String titlePrefix,
        BookStatus status,
        Integer first) {
}
~~~

~~~java
@QueryMapping
public List<Book> searchBooks(@Arguments BookSearchArguments arguments) {
    return bookService.search(
            arguments.titlePrefix(),
            arguments.status(),
            arguments.first());
}
~~~

**@Arguments** is useful when multiple arguments form a group of search criteria. If a method only needs one or two values, **@Argument** usually makes the intent clearer.

A `Map` is flexible but requires manual casting and null checks. A DTO is statically typed, easier to refactor, and more convenient for applying validation.

## 7. Distinguishing arguments from the source object

This is a very important point when writing **@SchemaMapping**.

An argument is data passed by the client for the current field. The source object is the result already resolved from the parent field and used as input to resolve the child field.

SDL:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author(language: String): Author
}

type Author {
  id: ID!
  name: String!
}
~~~

Controller:

~~~java
@Controller
public class BookController {

    private final BookService bookService;
    private final AuthorService authorService;

    public BookController(
            BookService bookService,
            AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(
            Book source,
            @Argument("language") String language) {

        return authorService.findById(
                source.getAuthorId(),
                language);
    }
}
~~~

In the `author` method:

- **Book source** is the parent object already resolved by `Query.book`.
- **@Argument("language")** is the argument of the `Book.author` field sent by the client.

Query:

~~~graphql
query {
  book(id: "book-01") {
    title
    author(language: "vi") {
      name
    }
  }
}
~~~

When `Query.book` returns a `Book`, GraphQL uses that `Book` as the source for the `author` field. Spring passes the source object into the `Book` parameter and reads `language` from the `author` field's argument.

Do not confuse the source object with an argument named `book`. The client does not need to send the entire `Book` back in the child query; the parent object is already available in the execution context.

## 8. Source type inference in `@SchemaMapping`

With **@SchemaMapping**, Spring can infer the GraphQL type containing the field from the handler's source object type:

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

In this example:

- The Java source type is `Book`.
- The method name is `author`.
- Spring can infer the mapping corresponding to `Book.author`.

If the method name differs from the field name or the source type is not clear enough, specify them explicitly:

~~~java
@SchemaMapping(typeName = "Book", field = "primaryAuthor")
public Author loadAuthor(Book source) {
    return authorService.findById(source.getAuthorId());
}
~~~

When a method accepts multiple parameters, ensure the source object is clearly identifiable. Parameters already annotated with annotations such as **@Argument** or having special types such as **DataFetchingEnvironment** are handled by their respective resolvers; the remaining parameter can be used as the source if it fits the mapping.

If the method signature is ambiguous or has multiple unresolvable parameters, Spring reports an error when discovering or invoking the handler. Avoid using multiple unannotated Java parameters expecting the framework to guess their meaning.

## 9. Preserving the distinction between omitted and `null` with `ArgumentValue`

For nullable arguments, GraphQL distinguishes two cases:

- The client did not send the argument.
- The client sent the argument with the value `null`.

In some update mutations, these two states have different meanings. For example, omitting `description` may mean keeping the old value, whereas sending `null` may mean clearing the description.

If you bind directly to a nullable `String` or DTO field, both cases can collapse into Java `null`. **ArgumentValue<T>** preserves whether the argument was omitted.

SDL:

~~~graphql
type Query {
  books(filter: BookFilterInput): [Book!]!
}
~~~

Handler:

~~~java
@QueryMapping
public List<Book> books(
        @Argument("filter") ArgumentValue<BookFilterInput> filter) {

    if (filter.isOmitted()) {
        return bookService.findDefaultBooks();
    }

    if (filter.value() == null) {
        return bookService.findBooksWithoutFilter();
    }

    return bookService.search(filter.value());
}
~~~

Here:

- Omitting `filter`: `ArgumentValue` indicates the argument was omitted.
- Passing `filter: null`: the argument is present, and its value is `null`.
- Passing an object: `value` holds the bound `BookFilterInput`.

If the SDL declares the argument as non-null, a valid client request cannot omit it or pass `null`; in that case, `ArgumentValue` is not needed to distinguish the two states.

`ArgumentValue` is especially useful for patch/update semantics. Test omitted, explicit `null`, and populated objects separately to avoid accidentally wiping data.

## 10. Receiving data from `GraphQLContext` with `@ContextValue`

`GraphQLContext` is a shared data container scoped to a single GraphQL execution. Data can be added from a `WebGraphQlInterceptor` or request-processing component before the operation runs.

Example handler reading a tenant ID:

~~~java
@QueryMapping
public List<Book> books(
        @ContextValue("tenantId") String tenantId) {

    return bookService.findForTenant(tenantId);
}
~~~

The `tenantId` value must be placed into `GraphQLContext` beforehand by the server. A handler should never blindly trust a tenant ID sent by the client in an argument.

An interceptor can read authenticated information and populate the execution input:

~~~java
@Component
public class TenantContextInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String tenantId = resolveTenantFromAuthenticatedRequest(request);

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(context ->
                        context.put("tenantId", tenantId))
                    .build());

        return chain.next(request);
    }
}
~~~

This is an illustrative example; how you resolve the tenant must be based on your application's authentication and multi-tenant model. `GraphQLContext` can be read across multiple handlers within the same execution without passing the tenant through every client argument.

If the key is missing, handling depends on the required/optional setting of **@ContextValue** and the parameter type. For mandatory data such as tenant or principal, fail fast instead of silently falling back to an unsafe default value.

## 11. Local context with `@LocalContextValue`

GraphQL also provides local context to pass data down a specific branch of the field tree. Unlike `GraphQLContext`, which is shared across the entire execution, local context is passed from a parent `DataFetcher` down to related child fields.

A `DataFetcher` can return **DataFetcherResult** containing both data and local context:

~~~java
DataFetcherResult<Book> result = DataFetcherResult.<Book>newResult()
        .data(book)
        .localContext(Map.of("displayCurrency", "VND"))
        .build();
~~~

The child field handler can receive the value:

~~~java
@SchemaMapping(typeName = "Book", field = "price")
public Money price(
        Book book,
        @LocalContextValue("displayCurrency") String currency) {

    return pricingService.convert(book.getPrice(), currency);
}
~~~

Local context is useful when information only makes sense within the branch being resolved, such as display locale, currency, or a processing option chosen at the parent field.

Do not use local context in place of core domain data. If data is a stable part of `Book` or `Author`, model it in the appropriate domain object or service. Context should hold execution-oriented metadata.

## 12. `DataFetchingEnvironment` for low-level access

If the annotated parameters are not enough, a handler can accept **DataFetchingEnvironment**:

~~~java
@QueryMapping
public Book book(
        @Argument("id") String id,
        DataFetchingEnvironment environment) {

    GraphQLContext graphQLContext = environment.getGraphQlContext();
    String operationPath = environment.getExecutionStepInfo()
            .getPath()
            .toString();

    return bookService.findById(id);
}
~~~

`DataFetchingEnvironment` provides extensive information:

- Arguments of the current field.
- Source object.
- `GraphQLContext` and local context.
- Field definition and selection set.
- `ExecutionStepInfo` and field path.
- GraphQL schema and execution details.

Example reading an argument directly:

~~~java
String id = environment.getArgument("id");
~~~

However, if a method only needs an argument, use **@Argument**. The annotation states clearly what data the method requires and keeps business code decoupled from the GraphQL Java API.

`DataFetchingEnvironment` fits adapters or resolvers that must branch behavior based on the selection set, execution path, or specific GraphQL metadata. Do not pass it deep into the service layer.

## 13. `Principal` and authentication information

When integrated with Spring Security, a handler can receive **Principal** if the request's principal is made available in the GraphQL execution context:

~~~java
@QueryMapping
public List<Book> myBooks(Principal principal) {
    return bookService.findOwnedBy(principal.getName());
}
~~~

`Principal` represents the authenticated identity. It differs from a client-sent argument:

- An argument is request data and can be modified by the client.
- `Principal` is produced by server-side authentication.

Do not rely on an argument like `userId` or `ownerId` as the sole basis for determining the caller's data. If the API allows querying another user's resources, the service must verify authorization for that resource.

If the request has no principal, the handler must handle unauthenticated access according to application policy. You can protect fields using Spring Security or method security and return consistent authorization errors.

## 14. Validation and errors during argument binding

There are multiple validation layers before a handler completes:

1. GraphQL parses and validates the operation.
2. GraphQL checks that arguments exist and match schema types.
3. GraphQL coerces variables and input literals.
4. Spring binds argument values to Java types.
5. Bean Validation checks constraints if enabled.
6. The service enforces business rules and permissions.

Example input:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Java record:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        @NotBlank String authorId) {
}
~~~

Handler:

~~~java
@MutationMapping
public Book createBook(
        @Argument("input") @Valid CreateBookInput input) {
    return bookService.create(input);
}
~~~

The application needs a Jakarta Bean Validation provider, typically via **spring-boot-starter-validation**. With Spring Boot 3, annotations belong to the **jakarta.validation** namespace.

### Binding errors vs. business errors

A binding error occurs when Spring cannot convert a GraphQL value into the target Java type or cannot bind the structure to the DTO. Examples include an incompatible constructor, an unconvertible Java type, or a mismatched input structure.

A business error occurs after data has bound successfully but violates a business rule, such as a nonexistent author ID or a user lacking update permission.

Do not treat the two error categories identically:

- Binding/validation errors typically reflect a request that violates the input contract.
- Business errors reflect domain state or use-case preconditions.

Spring for GraphQL can translate binding or validation errors into GraphQL errors through exception handling. If your API uses a payload object and wants to return validation errors inside the payload, convert them explicitly according to your contract; simply adding `@Valid` does not populate `userErrors` automatically.

## 15. Avoiding overuse of `DataFetchingEnvironment` and context

Method argument resolution lets handlers receive only the data they actually need. Signs that a handler depends too heavily on GraphQL execution include:

- A method accepts `DataFetchingEnvironment` just to read a simple argument.
- Services accept `DataFetchingEnvironment` or `GraphQLContext`.
- Multiple resolvers manually read the same header or parse authentication on their own.
- Business logic depends on field names or the selection set.
- Clients must send a tenant/user ID even though the server already authenticated the identity.

You can improve this by:

- Using **@Argument** for input data.
- Using the source object for child fields.
- Using **@ContextValue** for server-generated request metadata.
- Using `Principal` for authenticated identity.
- Mapping input into a command/query object before calling the service.
- Keeping `DataFetchingEnvironment` strictly in the adapter layer when GraphQL metadata is genuinely needed.

Example:

~~~java
@MutationMapping
public Book updateBook(
        @Argument("input") UpdateBookInput input,
        Principal principal) {

    UpdateBookCommand command = new UpdateBookCommand(
            input.id(),
            input.title(),
            principal.getName());

    return bookService.update(command);
}
~~~

The service receives a strongly typed command instead of depending on GraphQL arguments or the execution environment.

## 16. Method argument resolution in `@BatchMapping`

For a regular field resolver, the source object is typically a single object:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

With **@BatchMapping**, the handler receives a list of source objects:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    List<String> ids = books.stream()
            .map(Book::getAuthorId)
            .distinct()
            .toList();

    Map<String, Author> authors = authorService.findAllByIds(ids);

    Map<Book, Author> result = new HashMap<>();
    for (Book book : books) {
        Author author = authors.get(book.getAuthorId());
        if (author != null) {
            result.put(book, author);
        }
    }
    return result;
}
~~~

The **List<Book>** parameter here is not a list argument sent by the client. It is the batch of source objects collected by the framework to batch-resolve the `author` field.

Distinguish the two cases:

- **@Argument List<BookFilter>**: a list passed by the client into the field.
- **List<Book>** in a **@BatchMapping** handler: the list of parent/source objects collected by the framework.

If a field has its own arguments in the schema, review how your batch mapping and `DataLoader` are designed so each argument value is still applied properly per source or keyed appropriately.

## 17. Testing method argument resolution with `GraphQlTester`

`GraphQlTester` allows testing operations and handler outputs at the GraphQL execution level.

Example testing arguments and source objects:

~~~java
@SpringBootTest
class BookArgumentResolutionTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldBindArgumentAndResolveNestedField() {
        graphQlTester.document("""
                query FindBook($id: ID!) {
                    book(id: $id) {
                        title
                        author(language: "vi") {
                            name
                        }
                    }
                }
                """)
            .variable("id", "book-01")
            .execute()
            .path("book.author.name")
            .entity(String.class)
            .isEqualTo("Nguyen An");
    }
}
~~~

Tests should cover these scenarios:

1. Scalar arguments bind to the expected Java types.
2. Explicit argument names that differ from Java parameter names work properly.
3. Input objects bind to records/DTOs and nested objects.
4. `@Arguments` binds all fields, including schema default values.
5. Omitted arguments and explicit `null` are distinguished when using `ArgumentValue`.
6. Source object matches the expected result from the parent field.
7. `@ContextValue` receives data placed into context by an interceptor.
8. `@LocalContextValue` only receives data propagated along the corresponding branch.
9. `Principal` reflects the authenticated user.
10. Binding errors, Bean Validation errors, and business errors are handled properly.
11. `@BatchMapping` receives the source list and maps results back to the right parents.

For context tests, you can use `GraphQlTester`. When you need to test HTTP headers, authentication filters, or transport interceptors, add tests with `HttpGraphQlTester` or an appropriate client.

## 18. Common method argument resolution issues

| Symptom | Possible cause | Resolution |
|---|---|---|
| Argument is always `null` | Name in `@Argument` does not match the SDL | Specify the argument name explicitly |
| Record fails to bind | Constructor component does not match the input field or types are incompatible | Check the name and type of each component |
| Cannot distinguish omitted from `null` | Using a regular nullable Java field | Use `ArgumentValue` when presence matters |
| Source object is `null` or wrong type | Parent resolver returned unexpected data or mapping targets the wrong type | Check the parent field's output and `typeName` |
| `Map`/DTO is missing fields | Confusing `@Argument` with `@Arguments` or client did not send the field | Pick the right annotation and inspect variables |
| Context value is missing | Interceptor did not insert the key into `GraphQLContext` | Check context setup and key name |
| `Principal` is `null` | Request is unauthenticated or transport does not supply a principal | Check security integration |
| Binding exception before entering method | Value cannot be converted to the Java type | Check scalar and DTO types |
| Child field runs repeated queries | Source resolver calls repository per object | Consider `@BatchMapping`/`DataLoader` |
| Service depends on GraphQL API | Passing `DataFetchingEnvironment` deep into the domain | Convert into a plain Java command/query |

## 19. Workflow for designing handler method parameters

When creating a new handler:

1. Identify the GraphQL field and the arguments declared in the SDL.
2. Use **@Argument** for individual values or **@Arguments** for a whole group.
3. Use a record/DTO for structured input objects.
4. Choose Java types compatible with the scalar, enum, list, and input types.
5. With **@SchemaMapping**, accept the source object from the parent field.
6. Use **ArgumentValue** if you need to distinguish omitted from explicit `null`.
7. Use **@ContextValue**, **@LocalContextValue**, or `Principal` for appropriate context data.
8. Only use `DataFetchingEnvironment` when low-level execution information is needed.
9. Apply Bean Validation and handle binding errors intentionally.
10. Translate input into a command/query so the service remains independent of GraphQL.
11. With **@BatchMapping**, distinguish the source list from client-supplied list arguments.
12. Write `GraphQlTester` tests for binding, context, source, and error cases.

Method argument resolution is the bridge between GraphQL execution and Java handler methods. **@Argument** reads client-sent data; **@Arguments** binds all arguments; the source object provides the result from the parent field; context and `Principal` carry request metadata; `DataFetchingEnvironment` grants low-level execution access. By choosing the right resolver for each source, using clearly typed DTOs, and testing `null`/omitted cases, handlers remain readable and services stay decoupled from GraphQL.
