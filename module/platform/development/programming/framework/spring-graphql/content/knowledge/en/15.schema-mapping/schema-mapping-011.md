# Avoiding duplicate resolvers

## 1. What problems do duplicate resolvers cause?

In Spring for GraphQL, a resolver is the component that supplies data for a field in the GraphQL schema. An application may have many controllers and business modules, yet each field in the schema needs one clear resolution path. If multiple methods register to handle the same field, the application can hit mapping conflicts on startup. If different resolvers duplicate the same query or business rule, the codebase becomes hard to maintain and APIs can return inconsistent results.

For example, two controllers both declare a mapping for `Query.books`:

```java
@Controller
class BookQueryController {

    @QueryMapping
    public List<Book> books() {
        return bookRepository.findAll();
    }
}

@Controller
class CatalogQueryController {

    @QueryMapping
    public List<Book> books() {
        return catalogRepository.findAllBooks();
    }
}
```

Both methods target the `books` field of the `Query` root type. Spring for GraphQL cannot arbitrarily pick one method as the primary resolver. Registering duplicate mappings can cause GraphQL controller initialization to fail because the mapping is not unique.

Even when method names differ, two methods still conflict if both declare `@SchemaMapping(typeName = "Book", field = "author")`. What matters is the mapped GraphQL type and field pair, not the Java class name or method name.

## 2. One mapping per GraphQL field rule

When designing resolvers, designate one clear owner responsible for resolving each field. With annotation mappings, apply these rules:

- Each root field on `Query` has one `@QueryMapping` handler.
- Each root field on `Mutation` has one `@MutationMapping` handler.
- Each root field on `Subscription` has one `@SubscriptionMapping` handler.
- Each field on an object type has one `@SchemaMapping`, `@BatchMapping`, or appropriate property fetcher mechanism.
- Never register the same type/field across multiple controller annotations or multiple runtime wiring configurations.

For example, keep one controller owning the `Query.books` field:

```java
@Controller
public class BookQueryController {

    private final BookQueryService bookQueryService;

    public BookQueryController(BookQueryService bookQueryService) {
        this.bookQueryService = bookQueryService;
    }

    @QueryMapping
    public List<Book> books() {
        return bookQueryService.findAll();
    }
}
```

Other controllers can provide different fields or call the same service through a separate API flow. There is no need to create a second resolver for the same field just because another screen or business team wants similar data.

## 3. Declare mappings explicitly for easy identification

Spring for GraphQL can infer the field name from the method name and the type from the method context. This inference is convenient for small examples, but when a project has many controllers, declare `typeName` and `field` explicitly on important mappings.

Example SDL:

```graphql
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
```

Resolver:

```java
@Controller
public class BookController {

    private final BookQueryService bookQueryService;

    public BookController(BookQueryService bookQueryService) {
        this.bookQueryService = bookQueryService;
    }

    @QueryMapping(name = "book")
    public Book findBook(@Argument("id") String id) {
        return bookQueryService.findById(id).orElse(null);
    }
}
```

For nested fields, use `@SchemaMapping` to state the type and field clearly:

```java
@Controller
public class BookAuthorController {

    private final AuthorQueryService authorQueryService;

    public BookAuthorController(AuthorQueryService authorQueryService) {
        this.authorQueryService = authorQueryService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorQueryService.findById(book.authorId()).orElse(null);
    }
}
```

`@QueryMapping` is specialized for the `Query` root; `@SchemaMapping` can map a field of any object type. Explicitly stating the type and field lets reviewers immediately see which mapping a method owns.

## 4. Extract shared logic into a service

Two resolvers may need the same business rule, but they should never duplicate queries or call each other's controllers directly. Move shared logic into a service or domain component, then let each resolver delegate to that component.

For example, both a REST API and a GraphQL API need to look up books:

```java
@Service
public class BookQueryService {

    private final BookRepository bookRepository;

    public BookQueryService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    public Optional<Book> findById(String id) {
        return bookRepository.findById(id);
    }

    public List<Book> findByAuthorId(String authorId) {
        return bookRepository.findByAuthorId(authorId);
    }
}
```

GraphQL resolver:

```java
@Controller
public class BookGraphQlController {

    private final BookQueryService bookQueryService;

    public BookGraphQlController(BookQueryService bookQueryService) {
        this.bookQueryService = bookQueryService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookQueryService.findById(id).orElse(null);
    }
}
```

A REST controller can use the same service:

```java
@RestController
@RequestMapping("/api/books")
public class BookRestController {

    private final BookQueryService bookQueryService;

    public BookRestController(BookQueryService bookQueryService) {
        this.bookQueryService = bookQueryService;
    }

    @GetMapping("/{id}")
    public Book findById(@PathVariable String id) {
        return bookQueryService.findById(id).orElseThrow();
    }
}
```

This reuses data-access rules while keeping a dedicated controller per transport protocol. Never call one controller from another controller; controllers are the request-handling layer, whereas services are where business behavior is shared.

## 5. Multiple fields needing the same business operation

Sometimes two different GraphQL fields need the same kind of data. For example, both `Book.author` and `Review.author` need to look up an author. That is not a reason to register two resolvers for the same field; those are two distinct fields that can call the same service.

SDL:

```graphql
type Book {
    id: ID!
    authorId: ID!
    author: Author
}

type Review {
    id: ID!
    authorId: ID!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

Two explicit mappings:

```java
@Controller
public class AuthorFieldController {

    private final AuthorQueryService authorQueryService;

    public AuthorFieldController(AuthorQueryService authorQueryService) {
        this.authorQueryService = authorQueryService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author bookAuthor(Book book) {
        return authorQueryService.findById(book.authorId()).orElse(null);
    }

    @SchemaMapping(typeName = "Review", field = "author")
    public Author reviewAuthor(Review review) {
        return authorQueryService.findById(review.authorId()).orElse(null);
    }
}
```

The two methods map two different type/field pairs, yet share `AuthorQueryService`. This is the right way to reuse logic: share business rules and data access while keeping mappings clear per the schema.

If two fields genuinely share the same semantics and have an appropriate common parent abstraction, you can consider an interface in the schema. However, introducing an interface merely to save a few lines of resolver code is usually not worth it if it makes the GraphQL contract harder to understand.

## 6. Do not create resolvers for fields already readable from the object

Not every field needs its own resolver method. GraphQL Java can use the property data fetcher to read values from the source object through matching getters, properties, or accessors.

Example Java record:

```java
public record Book(
    String id,
    String title,
    String authorName) {
}
```

Schema:

```graphql
type Book {
    id: ID!
    title: String!
    authorName: String!
}
```

If the `Query.book` resolver returns a `Book` that already has these properties, Spring for GraphQL / GraphQL Java can read `id`, `title`, and `authorName` from the object without writing three separate `@SchemaMapping` methods.

Only add a resolver when a field needs extra processing, such as loading a relationship, enforcing access permissions, computing a value, or calling a service. Avoid writing resolvers that merely return an existing property when there is no extra business requirement.

Do not put sensitive data onto the source object under the assumption that clients cannot access it. If a field is not meant to be exposed, design the schema and authorization appropriately; the property data fetcher can read a property whenever that field is exposed.

## 7. Avoiding N+1 with `@BatchMapping`

A non-duplicate resolver can still cause performance issues. For example, a query fetching 30 books where each `Book.author` field calls a repository once generates one query for books plus many queries for authors. This is the N+1 problem.

`@BatchMapping` lets Spring for GraphQL group multiple source objects of the same field into a single batch operation. Example:

```java
@Controller
public class BookBatchController {

    private final AuthorQueryService authorQueryService;

    public BookBatchController(AuthorQueryService authorQueryService) {
        this.authorQueryService = authorQueryService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        List<String> authorIds = books.stream()
            .map(Book::authorId)
            .distinct()
            .toList();

        Map<String, Author> authorsById =
            authorQueryService.findAllByIds(authorIds);

        return books.stream()
            .filter(book -> authorsById.containsKey(book.authorId()))
            .collect(Collectors.toMap(
                Function.identity(),
                book -> authorsById.get(book.authorId())
            ));
    }
}
```

`@BatchMapping` is a batch field-mapping mechanism integrated by Spring with `DataLoader`. The method receives a list of source objects and returns a map from each source object to its corresponding field value. `AuthorQueryService.findAllByIds` is a batch method provided by the application.

In the example, books whose author is not found have no entry in the map; the corresponding field value is treated as absent. If you need to distinguish a missing author from missing data explicitly, define error policies or null values consistent with nullability in the SDL.

Do not register an additional `@SchemaMapping(typeName = "Book", field = "author")` alongside `@BatchMapping` for the same field. `@BatchMapping` already supplies the data fetcher for that mapping. Two mechanisms registering the same field can conflict.

## 8. When a shared `DataLoader` is needed

If you need finer control over batch loading or want to share one loader across multiple resolvers, register a `DataLoader` via `BatchLoaderRegistry` and invoke it from `@SchemaMapping`.

Registering a batch loader in Spring:

```java
@Configuration
public class DataLoaderConfig {

    public DataLoaderConfig(BatchLoaderRegistry registry,
                            AuthorQueryService authorQueryService) {
        registry.forTypePair(String.class, Author.class)
            .registerMappedBatchLoader((authorIds, environment) ->
                Mono.just(authorQueryService.findAllByIds(authorIds))
            );
    }
}
```

Resolver using the loader:

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<String, Author> authorLoader) {
    return authorLoader.load(book.authorId());
}
```

Spring for GraphQL supports injecting a `DataLoader` by matching name or type into the resolver method. This example assumes the loader is registered with key type `String` and value type `Author`; ensure the registration and resolver parameter match. With `registerMappedBatchLoader`, the result is keyed in a map, so it does not depend on result list ordering the way a list-returning batch loader does.

`DataLoader` is managed per GraphQL execution/request context, batching calls within a single operation. Never create a singleton `DataLoader` whose cache is shared across users, because data may depend on tenant or access permissions.

Choose `@BatchMapping` when batching serves a single field and you want concise configuration. Choose `BatchLoaderRegistry` when you need to reuse a loader across multiple resolvers or require custom batch loading control.

## 9. Avoiding duplicate registration between annotations and `RuntimeWiringConfigurer`

Spring for GraphQL allows registering field resolvers via annotated controllers or `RuntimeWiringConfigurer`. Both mechanisms can coexist in an application, but they should not own the same type/field pair.

Conflicting example:

```java
@Controller
class BookController {

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id).orElse(null);
    }
}
```

```java
@Bean
RuntimeWiringConfigurer duplicateBookFetcher(BookService bookService) {
    return wiring -> wiring.type(
        "Query",
        type -> type.dataFetcher("book", environment ->
            bookService.findById(environment.getArgument("id")).orElse(null)
        )
    );
}
```

Both register `Query.book`. Pick one mechanism to own the field. If you want annotated controllers, remove the manual data fetcher; if you want programmatic wiring, remove the corresponding mapping annotation.

`RuntimeWiringConfigurer` remains useful for custom scalars, `TypeResolver`, or other runtime configuration that does not overlap with controller fields. You can have multiple configurers for distinct responsibilities as long as they do not register overlapping fetchers for the same field.

## 10. Aliases and fragments do not create new resolvers

Some cases look like calling a field multiple times, yet they are not duplicate mappings.

Aliases allow clients to specify different response keys when calling the same field:

```graphql
query CompareBooks($firstId: ID!, $secondId: ID!) {
    first: book(id: $firstId) {
        id
        title
    }
    second: book(id: $secondId) {
        id
        title
    }
}
```

`first` and `second` are aliases in the operation. Both still invoke the `Query.book` schema field, so two separate resolvers are not needed.

Fragments also only reuse a selection set:

```graphql
fragment BookSummary on Book {
    id
    title
}

query BookCatalog {
    books {
        ...BookSummary
    }
}
```

`BookSummary` is not a field and needs no resolver. GraphQL expands the fragment during operation execution and resolves the actual fields in the schema.

## 11. Conventions for organizing controllers and services

When a module has many types, you can organize controllers by domain or by field group. What matters is that every mapping has one clear owner and business logic is not duplicated.

Example structure:

```text
graphql/
├── BookQueryController.java
├── BookFieldController.java
├── AuthorFieldController.java
└── OrderQueryController.java

application/
├── BookQueryService.java
├── AuthorQueryService.java
└── OrderQueryService.java
```

- `BookQueryController` owns root queries related to books.
- `BookFieldController` owns nested fields on `Book`.
- `AuthorFieldController` owns nested fields on `Author`.
- Services hold query or business logic that can be shared across multiple resolvers.

There is no need to split controllers just to keep few methods per file. If a controller retains clear responsibilities and has no duplicate mappings, keeping related fields together can be easier to follow. Prioritize domain boundaries and GraphQL field ownership.

## 12. Testing to detect duplicate resolvers and inconsistent behavior

Testing Spring context initialization catches mapping registration errors before the application receives traffic. If two handlers both own the same field, context startup can fail immediately when Spring for GraphQL detects the conflicting mapping.

Once the context starts cleanly, use `GraphQlTester` to test real operations:

```java
@SpringBootTest
@AutoConfigureHttpGraphQlTester
class BookMappingTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void resolvesBookAndAuthorFields() {
        graphQlTester.document("""
            query {
                book(id: "book-42") {
                    id
                    title
                    author {
                        id
                        name
                    }
                }
            }
            """)
            .execute()
            .path("book.author.name")
            .entity(String.class)
            .isEqualTo("Nguyen An");
    }
}
```

The example assumes the test context has fixtures or mock services returning the corresponding book and author. Add tests to verify:

- Each field is resolved once according to the expected mapping.
- Resolvers sharing a service return consistent results.
- Simple property fields work without redundant resolvers.
- Batch mappings collect multiple source objects and return the right value for each object.
- Fields without data adhere to nullability in the schema.
- Operations with aliases or fragments still invoke the right field mappings.
- The application starts cleanly with all controllers and runtime configurers.

When testing performance, measure repository or service call counts during an operation with many parent objects. A test that only checks the response payload is not enough to prove N+1 has been eliminated.

## 13. Common issues when avoiding duplicate resolvers

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Application fails on startup | Two controllers map the same type/field | Find mapping annotations with the same type and field pair and keep one handler |
| Field has both `@SchemaMapping` and `@BatchMapping` | Two mechanisms register the same field | Pick one mapping; use `@BatchMapping` if batching is needed |
| Annotation and `RuntimeWiringConfigurer` both map a field | Resolver is registered in two places | Choose either the annotation or the programmatic fetcher for that field |
| Two resolvers share logic yet produce different results | Duplicated queries or business rules | Move shared logic into the service/domain layer |
| Many Java methods with the same name hurt readability | Relying on type/field inference in large controllers | Declare `typeName` and `field` explicitly |
| Writing resolvers for every property | Not leveraging the property data fetcher | Only write mappings for fields needing custom logic |
| N+1 persists despite having a single resolver | Resolver runs once per source object | Use `@BatchMapping` or `DataLoader` |
| One controller calls another controller | Sharing logic at the wrong layer | Extract a shared service or domain component |
| `DataLoader` returns data for the wrong user | Cache shared across requests or missing tenant context | Use execution-scoped loaders and verify permissions in the batch service |

## 14. Checklist before finalizing schema mappings

- [ ] Every GraphQL type/field pair has one clear resolution mechanism.
- [ ] No two `@QueryMapping`, `@MutationMapping`, or `@SchemaMapping` handlers register the same field.
- [ ] The same field is not registered through both annotations and `RuntimeWiringConfigurer`.
- [ ] `@BatchMapping` is used instead of a single-item mapping when batching that field is required.
- [ ] Important mappings declare `typeName` and `field` explicitly.
- [ ] Shared business logic lives in the service or domain layer.
- [ ] Resolvers do not call other controllers.
- [ ] The property data fetcher is leveraged for fields readable directly from the object.
- [ ] Aliases and fragments are understood as operation constructs, not new resolvers.
- [ ] Context startup and operations are tested with `GraphQlTester`.
- [ ] Backend call counts are measured to detect N+1.

## Conclusion

Avoiding duplicate resolvers starts with cleanly managing mappings between GraphQL types and fields. Each field should have one component responsible for resolving it; never register the same field across multiple controllers or simultaneously via annotations and `RuntimeWiringConfigurer`. When multiple fields need the same logic, share a service or domain component instead of duplicating code or calling controllers from one another.

In Spring for GraphQL, `@QueryMapping` fits root queries, `@SchemaMapping` targets object type fields, and `@BatchMapping` handles batch field loading. For properties already present on an object, leverage the property data fetcher to avoid unnecessary resolvers. Combining clear ownership, shared services, and `GraphQlTester` tests keeps schema mappings maintainable, consistent, and conflict-free as the application grows.
