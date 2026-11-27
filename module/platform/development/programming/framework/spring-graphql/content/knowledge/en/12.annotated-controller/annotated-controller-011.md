# DataFetcher from Handler Methods

In GraphQL Java, a **DataFetcher** is the component that provides the value for a field when an operation is executed. Spring for GraphQL lets developers write ordinary Java methods in annotated controllers; the framework detects those methods and registers a corresponding DataFetcher for each field in the schema.

This approach keeps resolver code close to the application's business structure. Instead of manually creating a DataFetcher and interacting directly with DataFetchingEnvironment for every field, developers can use annotations such as **@QueryMapping**, **@MutationMapping**, **@SubscriptionMapping**, and **@SchemaMapping**. Spring handles locating methods, mapping arguments, passing source objects, and turning method return values into GraphQL results.

This lesson explains the relationship between handler methods and DataFetchers, mapping rules, how Spring resolves parameters, synchronous/asynchronous return types, error handling, field resolver optimization, and testing.

## 1. DataFetcher in GraphQL Java

A GraphQL operation can select many fields. For each field to execute, GraphQL Java invokes the **DataFetcher** registered in the schema to obtain its value.

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

When the client sends:

~~~graphql
query {
  book(id: "book-01") {
    id
    title
  }
}
~~~

GraphQL Java needs a DataFetcher for the **Query.book** field. The value returned by that DataFetcher becomes the source object for the child fields **Book.id** and **Book.title**. Child fields can be resolved by dedicated DataFetchers or the default property data fetcher.

In plain GraphQL Java, a DataFetcher can be registered directly:

~~~java
RuntimeWiring wiring = RuntimeWiring.newRuntimeWiring()
        .type("Query", typeWiring -> typeWiring
                .dataFetcher("book", environment -> {
                    String id = environment.getArgument("id");
                    return bookService.findById(id);
                }))
        .build();
~~~

This snippet shows that a DataFetcher receives **DataFetchingEnvironment**, reads arguments, and returns data. Spring for GraphQL still uses GraphQL Java's DataFetcher mechanism, but lets you declare the logic via handler methods while the framework handles the adapter layer.

## 2. Annotated Controllers Turn Methods into DataFetchers

A controller is marked with **@Controller**. Methods with Spring for GraphQL mapping annotations are discovered and registered as DataFetchers for the corresponding fields.

Example:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

The **book** method becomes the handler for the **Query.book** field. Spring creates a DataFetcher wrapping the method invocation, converts GraphQL arguments into Java parameters, invokes the method, and passes the returned result back to GraphQL Java.

General processing flow:

~~~mermaid
flowchart TD
    A[GraphQL operation] --> B[GraphQL Java executes field]
    B --> C[DataFetcher registered by Spring]
    C --> D[Annotated controller handler]
    D --> E[Resolve parameters]
    E --> F[Invoke Java method]
    F --> G[Service / repository]
    G --> H[Method result]
    H --> I[GraphQL continues resolving selection set]
    I --> J[Response]
~~~

Therefore, a handler method is not a new kind of GraphQL field. It is how Spring supplies a DataFetcher for a field already declared in the SDL.

### Role of AnnotatedControllerConfigurer

In the annotated controller mechanism, **AnnotatedControllerConfigurer** discovers controllers and handler methods, then registers DataFetchers into runtime wiring. Spring Boot normally auto-configures this component when the application uses the Spring for GraphQL starter.

Developers typically only need to:

1. Declare the SDL schema.
2. Mark the class as **@Controller**.
3. Annotate methods with the appropriate mapping annotations.
4. Provide the services that the methods need to call.

There is no need to manually create a DataFetcher for every method mapped in this way.

## 3. Core Mapping Annotations

Spring for GraphQL provides shorthand annotations for root operations and a general annotation for field mapping:

| Annotation | Default Mapped Field |
|---|---|
| **@QueryMapping** | Field on the **Query** root type |
| **@MutationMapping** | Field on the **Mutation** root type |
| **@SubscriptionMapping** | Field on the **Subscription** root type |
| **@SchemaMapping** | Field on the specified or inferred object type or interface |

Example SDL:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}

type Subscription {
  bookPublished: Book!
}
~~~

Controller:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public Book book(@Argument String id) {
        // Find a book
        return null;
    }

    @MutationMapping
    public Book createBook(@Argument CreateBookInput input) {
        // Create a book
        return null;
    }

    @SubscriptionMapping
    public Flux<Book> bookPublished() {
        // Emit newly published books
        return publisherOfBooks();
    }
}
~~~

**@QueryMapping** is equivalent to a **@SchemaMapping** on type **Query**; **@MutationMapping** and **@SubscriptionMapping** are likewise specialized declarations for their respective root operation types.

The method name is normally used as the field name unless another name is specified. If a Java method name differs from the field name in the SDL, declare it explicitly:

~~~java
@QueryMapping(name = "book")
public Book findBookById(@Argument("id") String bookId) {
    return bookService.findById(bookId);
}
~~~

Explicit naming lets Java code follow internal naming conventions without altering the GraphQL contract.

## 4. @SchemaMapping for Object Fields

Root mappings handle fields starting at Query, Mutation, or Subscription. When clients select nested fields on an object, you can use **@SchemaMapping**.

SDL:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author: Author
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
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }
}
~~~

When GraphQL executes **Book.author**, Spring invokes the **author** method. The **Book book** parameter is the source object returned by the parent field **Query.book**.

### Inferring typeName and field

You can omit certain attributes when the method name and source type are sufficiently clear:

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Spring can infer:

- **typeName** from the source object type **Book**.
- **field** from the method name **author**.

When you want to group mappings for one object type in the same controller, you can place **@SchemaMapping** at the class level:

~~~java
@Controller
@SchemaMapping(typeName = "Book")
public class BookFieldController {

    @SchemaMapping
    public Author author(Book book) {
        return null;
    }

    @SchemaMapping
    public List<Review> reviews(Book book) {
        return List.of();
    }
}
~~~

In this example, the methods map to fields of **Book**; field names are inferred from the method names. You can specify **field** explicitly when the Java name does not match the SDL name.

## 5. Rules for Mapping Methods to Fields

When the framework discovers a handler method, the mapping must determine two pieces of information:

1. The GraphQL type containing the field.
2. The field name to handle.

You can specify them directly:

~~~java
@SchemaMapping(typeName = "Book", field = "publishedAt")
public Instant publicationDate(Book source) {
    return source.getPublishedAt();
}
~~~

Or rely on convention:

~~~java
@SchemaMapping
public Instant publishedAt(Book book) {
    return book.getPublishedAt();
}
~~~

For root operations:

~~~java
@QueryMapping
public List<Book> books() {
    return bookService.findAll();
}
~~~

The method above maps to **Query.books**.

Mappings must match the types and fields in the schema. A method without an appropriate mapping annotation does not automatically become a GraphQL field merely because its name matches a field in the SDL.

If two handler methods are both registered for the same GraphQL field, the application can hit a conflict while building runtime wiring. Keep one clear mapping per field and use service methods to share logic across controllers when needed.

## 6. Resolving Handler Method Parameters

Spring for GraphQL supports many parameter types. The framework reads the GraphQL execution context and passes the appropriate values into the method.

Commonly used parameters:

| Parameter | Meaning |
|---|---|
| **@Argument** | Extracts a single argument of a GraphQL field |
| **@Arguments** | Binds all arguments into a Map or object |
| Source object | Result object from the parent field |
| **DataFetchingEnvironment** | Directly accesses the GraphQL execution environment |
| **@ContextValue** | Retrieves a value from GraphQLContext |
| **@LocalContextValue** | Retrieves a value from the field's local context |
| **Principal** | Request principal if present in the execution context |

You do not need to declare every parameter. Only accept what the handler actually needs.

### @Argument

With SDL:

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
        @Argument Boolean includeArchived) {

    return bookService.findById(bookId, includeArchived);
}
~~~

The argument name can be specified in the annotation. If omitted, Spring uses the Java parameter name from available metadata. To avoid relying on whether the compiler retains parameter names, specify the name explicitly whenever the mapping could be ambiguous.

### Binding Input Objects

SDL:

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
public record CreateBookInput(String title, String authorId) {
}
~~~

Handler:

~~~java
@MutationMapping
public Book createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
~~~

Spring binds the input object to a Java record/DTO. The Java structure must be compatible with the fields in the input type; the schema remains the contract deciding which values clients are allowed to send.

### Source Object

When resolving a child field, handlers typically receive the source object as a parameter:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book source) {
    return authorService.findById(source.getAuthorId());
}
~~~

The **Book source** parameter is not an argument sent by the client. It is the result already resolved at the parent level. Clearly distinguishing the source object from **@Argument** prevents confusion between parent data and inputs to the current field.

### DataFetchingEnvironment

When lower-level GraphQL information is needed, you can accept **DataFetchingEnvironment**:

~~~java
@QueryMapping
public Book book(
        @Argument String id,
        DataFetchingEnvironment environment) {

    String executionPath = environment.getExecutionStepInfo()
            .getPath()
            .toString();

    return bookService.findById(id);
}
~~~

**DataFetchingEnvironment** provides arguments, source, GraphQL context, selection set, field definition, and execution information. Use it only when GraphQL-level details are genuinely required; for ordinary parameters, specialized annotations keep method signatures much easier to read.

### GraphQL Context

Shared per-request information can be placed into GraphQLContext in an interceptor and then retrieved in a handler:

~~~java
@QueryMapping
public List<Book> books(
        @ContextValue("tenantId") String tenantId) {
    return bookService.findForTenant(tenantId);
}
~~~

**@ContextValue** reads a value from GraphQLContext. For values passed only within a single execution branch, you can use **@LocalContextValue**. Context keeps handlers from reading the HTTP request directly or depending on a specific transport.

## 7. Return Types of Handler Methods

Handler methods can return synchronous values or asynchronous/reactive types supported by Spring for GraphQL.

| Return Type | Example | Meaning |
|---|---|---|
| Object/DTO | **Book** | A single value for the field |
| Collection | **List<Book>** | A list of values |
| **CompletionStage<T>** | **CompletableFuture<Book>** | Asynchronous result |
| **Mono<T>** | **Mono<Book>** | Single reactive result |
| **Publisher<T>** | **Flux<BookEvent>** | Stream of values, especially useful for subscriptions |

Synchronous example:

~~~java
@QueryMapping
public Book book(@Argument String id) {
    return bookService.findById(id);
}
~~~

Asynchronous example:

~~~java
@QueryMapping
public CompletableFuture<Book> book(@Argument String id) {
    return bookService.findByIdAsync(id);
}
~~~

Example with Reactor:

~~~java
@QueryMapping
public Mono<Book> book(@Argument String id) {
    return bookService.findByIdReactive(id);
}
~~~

Spring for GraphQL integrates with Spring's async/reactive support to feed method results into GraphQL execution. Return types must match the field type in the schema. For example, a **Book** field needs a Book value; a **[Book!]!** field needs a collection or supported publisher capable of producing an appropriate list result.

### Subscriptions Returning Publisher

Subscriptions typically emit multiple results over time. A handler can return **Flux<T>** or **Publisher<T>**:

~~~graphql
type Subscription {
  bookPublished: Book!
}
~~~

~~~java
@SubscriptionMapping
public Flux<Book> bookPublished() {
    return bookEventService.bookPublished();
}
~~~

Each item emitted by the publisher triggers one execution of the subscription's selection set and one payload sent to the client. When the client cancels the subscription or the connection closes, the emission source must be cleaned up according to the lifecycle.

Do not return an infinite publisher for a Query or Mutation merely because reactive types are supported. Choose return types based on the semantics of the field and transport.

## 8. Handler-Method DataFetchers in Runtime Wiring

Spring does not turn Java methods into new fields in the SDL. The SDL must still declare the field:

~~~graphql
type Query {
  books: [Book!]!
}
~~~

Handler method:

~~~java
@QueryMapping
public List<Book> books() {
    return bookService.findAll();
}
~~~

The annotated controller infrastructure registers a DataFetcher for **Query.books**. When GraphQL executes the field, the DataFetcher calls the handler method and returns the result to GraphQL Java.

This means:

- The SDL determines which fields exist and their data types.
- Annotations determine which method handles which field.
- Parameter resolvers convert execution data into Java parameters.
- The handler method calls a service and returns the result.
- GraphQL Java continues processing the result according to the selection set and schema.

If a field is declared in the SDL without an annotated handler, GraphQL can still use the default property data fetcher depending on the source object. For a root Query with no useful source object, an appropriate DataFetcher is needed to return data.

## 9. When to Use @SchemaMapping vs. @BatchMapping

**@SchemaMapping** typically processes one source object per invocation. If a query fetches many parent objects and each child field queries the database individually, an N+1 problem can occur.

Example:

~~~graphql
type Query {
  books: [Book!]!
}

type Book {
  id: ID!
  author: Author!
}
~~~

Regular handler:

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

If the query returns 100 Books, the method can be invoked 100 times. When data loading needs to be batched, Spring for GraphQL provides **@BatchMapping**:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    List<String> authorIds = books.stream()
            .map(Book::getAuthorId)
            .distinct()
            .toList();

    Map<String, Author> authors =
            authorService.findAllByIds(authorIds);

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

**@BatchMapping** is a way to declare a batch loader based on a handler method. The framework collects source objects and distributes results back to each source. For more complex scenarios or when loaders must be shared, you can use DataLoader directly.

Not every field needs batch mapping. If a field is an existing property on the source object, the default property data fetcher is usually enough. Use batching when per-source data loading has cost and multiple loads can be combined into a more efficient operation.

## 10. Handling Exceptions from Handler Methods

If a handler method throws an exception, the error is passed into GraphQL execution error handling. Internal exceptions or stack traces must never appear directly in production responses.

You can handle exceptions in the controller using **@GraphQlExceptionHandler**:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(BookNotFoundException exception) {
        return GraphqlErrorBuilder.newError()
                .message("Book not found")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }
}
~~~

To share error handling across multiple controllers, you can combine **@ControllerAdvice** with **@GraphQlExceptionHandler**, or implement **DataFetcherExceptionResolver**.

When designing errors, ensure you:

- Return messages appropriate for clients.
- Use consistent error classifications/codes.
- Never expose SQL, tokens, stack traces, or infrastructure details.
- Log server-side with a correlation ID when investigation is needed.
- Understand that GraphQL can return partial data alongside errors depending on the field and nullability.

## 11. Validation and Security on Handler Methods

A handler method is an appropriate boundary for receiving input and coordinating a use case, but do not cram all business rules into controllers.

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

Java:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        @NotBlank String authorId) {
}
~~~

Handler:

~~~java
@MutationMapping
public Book createBook(@Argument("input") @Valid CreateBookInput input) {
    return bookService.create(input);
}
~~~

The schema validates types and required fields. Bean Validation checks constraints like **@NotBlank**; the service checks that the author exists, user permissions, and business rules.

Method security can be applied on handlers or services:

~~~java
@PreAuthorize("hasAuthority('BOOK_EDITOR')")
@MutationMapping
public Book createBook(@Argument("input") @Valid CreateBookInput input) {
    return bookService.create(input);
}
~~~

The application must enable and configure method security accordingly. For business operations invoked from multiple adapters, placing final authorization checks in the service ensures policies are applied consistently.

Never read a tenant or role from client-supplied arguments and trust it directly. Use the authenticated principal or server-created context.

## 12. Organizing Controllers and Services

A controller should focus on mapping and forwarding necessary data. Business logic should reside in services:

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public List<Book> books(@Argument Integer first) {
        return bookService.findFirst(first);
    }
}
~~~

A controller can group related handlers, without turning into a dumping ground for all read/write data logic. You can split controllers by domain or operation group to make mappings easy to locate and test.

Do not inject repositories into every controller when services already encapsulate business rules. Controllers should be responsible for translating GraphQL requests into use-case calls and returning results matching the schema.

## 13. Common Mapping Errors

| Symptom | Possible Cause | How to Fix |
|---|---|---|
| Field is not resolved | Missing mapping annotation or wrong type/field name | Check SDL and annotations |
| Handler is not discovered | Class is not a Spring bean or missing **@Controller** | Register controller in the application context |
| Method maps to wrong field | Incorrect default name inference | Specify **typeName** and **field** explicitly |
| Java argument receives null | Argument name mismatch or client omitted it | Check SDL, operation, and **@Argument** |
| Source object has wrong type | Mapping placed on wrong type or resolver returned wrong object | Check output type of parent field |
| Multiple handlers for one field | Duplicate mapping | Keep one handler mapping per field |
| Query triggers many database queries | Child field resolver calls service per source | Use **@BatchMapping** or DataLoader |
| Subscription emits no events | Handler does not return a suitable Publisher or source emits nothing | Check publisher and lifecycle |
| Exception leaks internal info | GraphQL error is not normalized | Use an exception handler or resolver |
| Property fetcher unexpectedly overridden | Explicit mapping exists for a field normally read from a property | Check whether the field needs a custom resolver |

## 14. Testing Annotated Handler Methods

Spring for GraphQL provides **GraphQlTester** and transport-specific test variants. You can test handlers at the GraphQL level without sending actual HTTP requests:

~~~java
@SpringBootTest
class BookQueryControllerTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldResolveBook() {
        graphQlTester.document("""
                query FindBook($id: ID!) {
                    book(id: $id) {
                        id
                        title
                    }
                }
                """)
            .variable("id", "book-01")
            .execute()
            .path("book.title")
            .entity(String.class)
            .isEqualTo("Spring GraphQL");
    }
}
~~~

You should verify:

1. Handlers are registered properly for their fields in the SDL.
2. Arguments and input objects are bound properly.
3. Source objects are passed properly to field mappings.
4. Method results match schema return types.
5. Async/reactive results are handled properly.
6. Exceptions map to the expected GraphQL errors.
7. Field resolvers do not access unauthorized data.
8. Batch mappings reduce data loads and preserve source-result correspondence.
9. Subscriptions emit events and clean up when clients cancel.
10. Duplicate mappings or schema mismatches are caught when starting the application context.

If the goal is testing HTTP headers, endpoint paths, serialization, or web-stack security filters, add tests using **HttpGraphQlTester** or an appropriate test client. Execution-level **GraphQlTester** does not completely replace transport testing.

## 15. Workflow for Creating a DataFetcher with a Handler Method

When implementing a new field:

1. Declare the field and its data type in the SDL.
2. Choose a root mapping (**@QueryMapping**, **@MutationMapping**, **@SubscriptionMapping**) or **@SchemaMapping**.
3. Place the handler in a Spring **@Controller** class.
4. Specify **typeName**/**field** when you do not want default names.
5. Declare parameters using **@Argument**, source object, context, or execution environment as needed.
6. Call a service to execute the use case.
7. Choose a synchronous, async, or reactive return type based on field semantics.
8. Handle validation, authorization, and exceptions at the appropriate layers.
9. Consider N+1 issues and use **@BatchMapping**/DataLoader when loads can be batched.
10. Write GraphQlTester tests to verify mappings and results.

Annotated controllers let Spring for GraphQL turn handler methods into DataFetchers without forcing developers to manage all GraphQL Java wiring manually. The SDL still defines the contract; annotations connect fields to methods; parameter resolvers provide arguments, sources, and context; methods call services and return results so GraphQL can continue executing the selection set. Keeping controllers focused on mapping, placing business logic in services, and testing at the GraphQL level makes resolvers easier to read, maintain, and keep consistent.
