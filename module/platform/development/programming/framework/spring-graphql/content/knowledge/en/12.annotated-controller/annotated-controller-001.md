# @Controller in Spring GraphQL

Spring for GraphQL allows mapping fields in a GraphQL schema to Java methods using annotations. A bean marked with **@Controller** is where methods handling Query, Mutation, Subscription, and object type fields are typically placed. Spring discovers this bean during component scanning and then registers the methods annotated with GraphQL annotations so that they become schema resolvers.

The controller is the layer that connects the GraphQL contract to the business layer. It receives arguments from an operation, calls the appropriate service, and returns the result to the GraphQL runtime. The controller does not need to manually parse query strings or build JSON responses; GraphQL Java executes the operation and builds the response based on the schema.

## Role of @Controller

In the Spring Framework, **@Controller** is a stereotype annotation belonging to the component group. It marks a class as a Spring-managed component and allows component scanning to discover the class and create a bean. Spring for GraphQL uses managed controller beans to find methods annotated with annotations such as:

- **@QueryMapping**: handles fields on the Query root.
- **@MutationMapping**: handles fields on the Mutation root.
- **@SubscriptionMapping**: handles fields on the Subscription root.
- **@SchemaMapping**: handles fields of a specific object type.
- **@BatchMapping**: resolves a field for multiple source objects in a batch.

For example, a controller can declare a method to handle the book field:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

When a client sends a query selecting the book field, Spring for GraphQL invokes the corresponding method. The returned value continues to be resolved by the GraphQL runtime according to the fields requested by the client.

**@Controller is not an annotation that defines an HTTP endpoint.** It does not replace @PostMapping or @GetMapping in an MVC application. With GraphQL, the transport handler receives requests at the GraphQL endpoint, while the annotations on the controller map operations or fields within the schema.

## How @Controller Differs from @RestController

@Controller and @RestController are both Spring MVC stereotypes, but their typical purposes differ:

| Annotation | Common Purpose |
| --- | --- |
| **@Controller** | Declares a Spring MVC controller or an annotated GraphQL controller |
| **@RestController** | Declares a REST controller, combining @Controller and @ResponseBody |

Spring for GraphQL looks for controller beans that have methods annotated with GraphQL annotations. Therefore, use @Controller for annotated GraphQL controllers. @RestController is not a necessary choice for GraphQL resolvers; @ResponseBody is also not used to format GraphQL responses. The GraphQL runtime builds responses on its own according to the schema.

An application can provide both a REST API and a GraphQL API at the same time. In that case, REST controllers handle HTTP mappings such as @GetMapping, while GraphQL controllers handle fields with @QueryMapping or @SchemaMapping. Both types of controllers can coexist in a single Spring application context.

## Component Scanning and Controller Placement

Spring Boot typically starts component scanning from the package containing the class annotated with @SpringBootApplication and scans its subpackages. Therefore, GraphQL controllers should be placed beneath the root package of the application:

~~~text
com.example.catalog
├── CatalogApplication.java
├── graphql
│   ├── BookController.java
│   └── AuthorController.java
├── service
│   ├── BookService.java
│   └── AuthorService.java
└── repository
    └── BookRepository.java
~~~

Example startup class:

~~~java
@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

If a controller is outside the scanned packages, Spring does not create a bean for that class. In that case, the resolver methods are not registered, and the application may fail with an error indicating that no data fetcher was found for the field or exhibit unexpected default behavior.

You can configure the component scanning scope with @ComponentScan when the application has a special package structure. However, check the package of the @SpringBootApplication class and the controller location first to avoid unnecessarily broad scanning configuration.

## Declaring the Schema and Corresponding Controller

Suppose a book management API has the following schema:

~~~graphql
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}

type Book {
  id: ID!
  title: String!
  publishedYear: Int
}

input CreateBookInput {
  title: String!
  publishedYear: Int
}
~~~

The book and books fields belong to Query; createBook belongs to Mutation. The Book object describes the returned data, while CreateBookInput describes the data sent by the client.

The controller can be implemented as follows:

~~~java
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

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }

    @MutationMapping
    public Book createBook(@Argument CreateBookInput input) {
        return bookService.create(input);
    }
}
~~~

Spring manages BookController as a bean. Constructor injection provides BookService; GraphQL annotations determine which method handles which field. When a client sends a valid operation, GraphQL Java finds the data fetcher registered by Spring and invokes the corresponding controller method.

## @QueryMapping

**@QueryMapping** maps a method to a field on the Query root. If no name is passed in the annotation, Spring uses the method name as the field name:

~~~java
@QueryMapping
public Book book(@Argument String id) {
    return bookService.findById(id);
}
~~~

The method above handles the book field in the schema. You can specify the field name explicitly when the Java method name differs from the schema name:

~~~java
@QueryMapping(name = "featuredBooks")
public List<Book> findFeatured() {
    return bookService.findFeatured();
}
~~~

With this declaration, the featuredBooks field in Query is mapped to the findFeatured method. The field name in the SDL must still exist, and the method's return type must be compatible with the declared type.

## @MutationMapping and @SubscriptionMapping

**@MutationMapping** maps a method to a field on the Mutation root. For example:

~~~java
@MutationMapping
public Book renameBook(
        @Argument String id,
        @Argument String title) {
    return bookService.rename(id, title);
}
~~~

Mutations should call a service to perform business rules, validation, and data changes. Complex update logic should not be placed directly in the controller.

**@SubscriptionMapping** maps a method to a field on the Subscription root. Subscription methods typically return a reactive publisher such as Flux:

~~~java
@SubscriptionMapping
public Flux<Book> bookCreated() {
    return bookEventService.bookCreated();
}
~~~

Corresponding schema:

~~~graphql
type Subscription {
  bookCreated: Book!
}
~~~

For clients to receive events, the application must also configure a transport that supports subscriptions, such as WebSocket. Simply declaring the annotation or the Subscription root type does not automatically establish an event-streaming connection.

## @SchemaMapping for Object Type Fields

A GraphQL object can contain fields linking to other objects. When a field needs to call a service or query a data source, use **@SchemaMapping**:

~~~graphql
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

Resolver for the author field:

~~~java
@Controller
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
~~~

The Book parameter is the source object, meaning the parent object that GraphQL is currently resolving. Spring passes that object into the method so the resolver can obtain authorId. The annotation explicitly specifies the source type Book and the field author.

If typeName or field is not specified, Spring can infer the names from the source parameter type and the method name. For example, the method author(Book book) is typically understood as the author field of type Book. When the schema is large or Java names do not match SDL names, explicit declaration makes the mapping easier to read and less error-prone.

If the Java object has a property corresponding to a field in the schema, GraphQL can read the value via the default property access without writing @SchemaMapping. Create a separate resolver when a field needs to query data, call a service, apply logic, or retrieve a value from another source.

## Receiving Arguments with @Argument

GraphQL fields can accept arguments. The **@Argument** annotation extracts an argument value from the operation and converts it to a Java type:

~~~graphql
type Query {
  book(id: ID!): Book
  searchBooks(keyword: String!, limit: Int = 10): [Book!]!
}
~~~

~~~java
@QueryMapping
public Book book(@Argument("id") String bookId) {
    return bookService.findById(bookId);
}

@QueryMapping
public List<Book> searchBooks(
        @Argument String keyword,
        @Argument Integer limit) {
    return bookService.search(keyword, limit);
}
~~~

The name in @Argument must match the argument name in the SDL. You can omit the name when Java parameter names are preserved and Spring can infer it accurately. When the Java name differs from the schema name, specify the name explicitly, such as @Argument("id").

For input objects, you can receive the entire object with a single parameter:

~~~java
public record CreateBookInput(String title, Integer publishedYear) {
}

@MutationMapping
public Book createBook(@Argument CreateBookInput input) {
    return bookService.create(input);
}
~~~

Spring converts the input object into the corresponding Java type through its conversion and binding mechanism. The Java structure must be compatible with the fields and types in the SDL. If the input contains complex data, use a dedicated DTO or record instead of binding directly to a persistence entity.

## Special Parameters in Annotated Controllers

In addition to arguments and source objects, a resolver method may need the execution context. Spring for GraphQL supports several special parameter types, for example:

| Parameter | How to Receive | Purpose |
| --- | --- | --- |
| Argument | @Argument | Retrieves a field argument |
| Source object | Parent object parameter, typically an unannotated input parameter | Resolves nested fields |
| GraphQLContext | GraphQLContext type | Reads context data of the operation |
| Context value | @ContextValue | Retrieves a value by key from GraphQLContext |
| Local context value | @LocalContextValue | Retrieves a value from the local context passed between fields |
| DataFetchingEnvironment | DataFetchingEnvironment parameter | Accesses execution information for the current field |
| Principal | Principal parameter | Accesses the authenticated principal if present |

Example of retrieving a value from the GraphQL context:

~~~java
@QueryMapping
public List<Book> myBooks(@ContextValue("tenantId") String tenantId) {
    return bookService.findByTenant(tenantId);
}
~~~

The context must be populated at the request or interceptor layer before the resolver reads the value. If the key does not exist, clearly decide how to handle null values or provide an appropriate default.

You can access DataFetchingEnvironment when more detailed information is needed:

~~~java
@QueryMapping
public Book book(
        @Argument String id,
        DataFetchingEnvironment environment) {
    GraphQLContext context = environment.getGraphQlContext();
    return bookService.findById(id);
}
~~~

Do not use DataFetchingEnvironment in place of every parameter. Prefer @Argument and specialized parameter types so that the resolver signature clearly expresses the data it needs.

## Constructor Injection and Service Organization

Controllers should focus on GraphQL field mapping, while business logic should reside in services. Constructor injection makes required dependencies explicit and aids testing:

~~~java
@Service
public class BookService {

    private final BookRepository bookRepository;

    public BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    public Book findById(String id) {
        return bookRepository.findById(id).orElse(null);
    }

    public List<Book> findAll() {
        return bookRepository.findAll();
    }
}
~~~

In the example, the service coordinates the repository and can contain validation, transactions, or business rules. The controller calls the service and returns the result to the GraphQL runtime. Separating layers by responsibility allows the same business logic to be used from GraphQL, REST, or message consumers.

Do not store request data in mutable fields of a controller. Spring beans typically have singleton scope, so multiple requests can invoke the same controller instance concurrently. Per-request data should be passed through parameters, context, or a bean with an appropriate scope.

## Resolver Return Types

Annotated controllers can return synchronous or asynchronous values. Common types include:

| Return Type | Meaning |
| --- | --- |
| Java object or scalar | Synchronous result |
| Collection or List | Multiple values returned as a list |
| Mono<T> | Reactive result with at most one value |
| Flux<T> | Reactive stream consisting of multiple values |
| CompletionStage<T> | Asynchronous result using Java CompletionStage |

Example reactive resolver:

~~~java
@Controller
public class ReactiveBookController {

    private final ReactiveBookService bookService;

    public ReactiveBookController(ReactiveBookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Mono<Book> book(@Argument String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public Flux<Book> books() {
        return bookService.findAll();
    }
}
~~~

The GraphQL runtime coordinates asynchronous results during execution. Using Mono or Flux does not automatically make a blocking operation non-blocking; services and repositories must support reactive execution if you want to maintain a non-blocking model end to end.

## Batch Mapping for Related Fields

When a query fetches multiple objects and each object needs a related field, a regular resolver can cause an N+1 problem. **@BatchMapping** allows resolving that field in groups:

~~~java
@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        return authorService.findAuthorsFor(books);
    }
}
~~~

The method receives a list of source objects and returns the corresponding result for each Book. The service needs to perform actual batch queries to reduce the number of accesses to the database or external services. Details of DataLoader and batch loading should be designed together with the service/repository layer.

## Security on Controllers

The controller is one place where method security can be applied to resolvers. For example:

~~~java
@Controller
public class AdminGraphQlController {

    @PreAuthorize("hasRole('ADMIN')")
    @QueryMapping
    public List<AuditEntry> auditLog() {
        return auditService.findRecentEntries();
    }
}
~~~

For the @PreAuthorize annotation to take effect, the application must enable method security in the Spring Security configuration. Access permissions should be checked by user, object, and field; authenticating only at the HTTP endpoint is not sufficient for queries with many nested fields.

## Error Handling in Annotated Controllers

Resolvers can throw exceptions when data is not found, input is invalid, or an external service fails. Spring for GraphQL supports error handling through mechanisms such as DataFetcherExceptionResolver or @GraphQlExceptionHandler in annotated controllers.

For example, a handler can translate a business exception into a GraphQL error with an appropriate message:

~~~java
@Controller
public class GraphQlErrorHandler {

    @GraphQlExceptionHandler
    public GraphQLError handle(BookNotFoundException exception) {
        return GraphqlErrorBuilder.newError()
                .message("Book not found")
                .errorType(ErrorType.NOT_FOUND)
                .build();
    }
}
~~~

Specific API names and signatures must match the Spring for GraphQL version in the project. Messages sent to clients must not contain stack traces, SQL queries, tokens, or internal information. For validation, return errors clear enough for the client to know which field or input is invalid.

## Testing Annotated Controllers

Spring for GraphQL provides GraphQlTester to test operations without manually building and parsing JSON responses. For example:

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
    .path("book.title")
    .entity(String.class)
    .isEqualTo("Spring in Action");
~~~

You should test valid mappings, missing or invalid arguments, non-existent data, access permissions, exceptions, and nested fields. If you need to test the full HTTP transport, you can use HttpGraphQlTester combined with WebTestClient or an appropriate tester for the application's web stack.

## Common Errors When Using @Controller

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Resolver is not invoked | Controller is not component-scanned or is missing mapping annotation | Check package and bean registration |
| Field has no matching data fetcher | Field name or typeName does not match SDL | Check @QueryMapping, @SchemaMapping, and schema |
| Argument receives null | @Argument name is wrong or client did not pass the variable | Compare argument names in SDL and operation |
| Input object fails to bind | Java type is incompatible with SDL structure | Check DTO, constructor, and field types |
| Nested field returns null | Property accessor or child resolver does not provide a value | Check source object and @SchemaMapping |
| Request is blocked on event loop | Reactive resolver calls a blocking library | Check service/repository and scheduler usage |
| Method security does not work | Method security is not enabled or method does not go through proxy | Check Spring Security configuration |

## Principles for Organizing Annotated Controllers

When building GraphQL controllers, keep a few principles in mind:

1. **Use @Controller for annotated GraphQL handlers.** Place classes in packages covered by Spring component scanning.
2. **Map clearly according to the schema.** Method names, fields, typeName, and arguments must match the SDL.
3. **Keep controllers thin.** Controllers receive input, call services, and return results; business logic lives in services.
4. **Use constructor injection.** Declare required dependencies clearly and keep them easy to test.
5. **Choose appropriate return types.** Use reactive publishers when the underlying layers support non-blocking execution.
6. **Protect fields according to access permissions.** Combine Spring Security with permission checks at the service or data access layer.
7. **Test actual operations.** Cover queries, mutations, subscriptions, field mappings, and errors according to API requirements.

In Spring for GraphQL, @Controller is the focal point for organizing resolvers according to Spring's bean model. Mapping annotations link Java methods to fields in the SDL; arguments and source objects provide data to methods; services handle business logic; and the GraphQL runtime coordinates execution and produces responses. Keeping these boundaries clear makes controllers easy to read, easy to test, and extensible as the schema grows.
