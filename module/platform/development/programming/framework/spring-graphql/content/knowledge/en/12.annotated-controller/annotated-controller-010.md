# Multiple Controllers for One Schema

## Objectives

After this lesson, you can:

- Explain why a single GraphQL schema can be handled by multiple Spring controllers.
- Split resolvers by root field, object type, or business domain.
- Use `@QueryMapping`, `@MutationMapping`, and `@SchemaMapping` across separate controllers.
- Understand how Spring discovers controllers and registers mappings for GraphQL fields.
- Avoid conflicts when multiple controllers declare resolvers for the same field.
- Test multiple controllers participating together in executing a single GraphQL operation.

## One Schema Does Not Require a Single Controller

In Spring for GraphQL, the SDL schema describes the API contract, while annotated controllers provide resolvers for the fields. A single schema can have multiple controller beans participating together to handle requests.

For example, a library API has features for reading books, reading authors, fetching a book's author, and creating books. You can split resolvers into `BookQueryController`, `AuthorQueryController`, `BookFieldController`, and `BookMutationController`. These controllers still serve the same schema and the same GraphQL endpoint.

Keep in mind that controllers are a server-side code organization mechanism. They do not create separate schemas, separate GraphQL URLs, or change how clients write operations.

## Shared Schema for Multiple Controllers

Suppose the library API has the schema:

~~~graphql
type Query {
  bookById(id: ID!): Book
  booksByAuthor(authorId: ID!): [Book!]!
  authorById(id: ID!): Author
}

type Mutation {
  registerBook(input: RegisterBookInput!): Book!
  renameAuthor(id: ID!, name: String!): Author!
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

input RegisterBookInput {
  title: String!
  authorId: ID!
}
~~~

The schema has one `Query` root type and one `Mutation` root type. Each field can be mapped to a method in a different controller. `Book.author` is a nested field that can have its own resolver in a controller dedicated to handling fields of `Book`.

One operation can traverse multiple controllers during a single execution:

~~~graphql
query BookDetails($id: ID!) {
  bookById(id: $id) {
    id
    title
    author {
      id
      name
    }
  }
}
~~~

The `bookById` root field can be handled by `BookQueryController`. When GraphQL continues resolving the `author` field, a method in `BookFieldController` is invoked. The `name` field can be read directly from the `Author` object if the object already has a matching property or getter.

## How Spring Discovers Multiple Controllers

An annotated GraphQL controller is a Spring bean marked with `@Controller`:

~~~java
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {
    // Mapping methods for GraphQL fields.
}
~~~

Spring for GraphQL discovers controller beans in the application context and registers methods annotated with `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping`, or `@SchemaMapping`.

Therefore, controllers must be discovered by Spring component scanning. If a class lies in a subpackage of the package containing the `@SpringBootApplication` class, the default component scan configuration normally covers it. If you place controllers outside the scan scope, adjust `@ComponentScan` or the package layout so the beans are registered.

Example package structure:

~~~text
com.example.library
├── LibraryApplication.java
├── graphql
│   ├── book
│   │   ├── BookQueryController.java
│   │   ├── BookFieldController.java
│   │   └── BookMutationController.java
│   └── author
│       ├── AuthorQueryController.java
│       └── AuthorMutationController.java
├── application
│   ├── BookService.java
│   └── AuthorService.java
└── domain
    ├── Book.java
    └── Author.java
~~~

With `LibraryApplication` located in `com.example.library`, controllers inside `com.example.library.graphql` are discovered by the default component scan. Organizing packages this way groups resolvers by business domain while keeping services and domain models independent of the GraphQL layer.

## Splitting Root Queries into Multiple Controllers

Root fields belonging to the same `Query` can be split by data type or use case. For example, `BookQueryController` handles only book-related queries:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

import java.util.List;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id).orElse(null);
    }

    @QueryMapping
    public List<Book> booksByAuthor(
            @Argument("authorId") String authorId) {
        return bookService.findByAuthorId(authorId);
    }
}
~~~

Meanwhile, `AuthorQueryController` handles the `authorById` field:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class AuthorQueryController {

    private final AuthorService authorService;

    public AuthorQueryController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @QueryMapping
    public Author authorById(@Argument("id") String id) {
        return authorService.findById(id).orElse(null);
    }
}
~~~

The two methods belong to two different beans, yet both map onto the `Query` root type. Spring for GraphQL registers resolvers based on the GraphQL type and field name, not on the controller class name.

The method name is used as the field name by default. If you want the Java name to differ from the field name in the SDL, you can declare an explicit name:

~~~java
@QueryMapping(name = "bookById")
public Book findBook(@Argument("id") String bookId) {
    return bookService.findById(bookId).orElse(null);
}
~~~

When using an explicit name, make sure it matches the field in the schema exactly. The Java method name does not need to match the field name if the mapping specifies it explicitly.

## Separating Resolvers for Nested Fields

Not every resolver belongs to the `Query` or `Mutation` root. Fields on object types can be placed in separate controllers. For example, `Book.author` is handled in `BookFieldController`:

~~~java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
@SchemaMapping(typeName = "Book")
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.authorId()).orElse(null);
    }
}
~~~

Class-level `@SchemaMapping(typeName = "Book")` sets the default GraphQL object type for mapping methods in the controller. `@SchemaMapping` on the `author` method uses the method name as the field name, so it maps to `Book.author`.

The `Book book` parameter is the source object that GraphQL is currently resolving. Spring for GraphQL passes the parent object into the method automatically; there is no need to declare `@Argument` for the source object.

If you do not want to set a default mapping at the class level, you can declare it completely on the method:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author resolveBookAuthor(Book source) {
    return authorService.findById(source.authorId()).orElse(null);
}
~~~

The second style is useful when the method name differs from the GraphQL field or when one controller handles fields belonging to several different object types.

You do not need to write resolvers for every field. If the Java object already has a matching property or getter, GraphQL can read the value via the default property data fetcher. Create a `@SchemaMapping` only when you need to query another data source, transform the result, or run additional logic.

## Splitting Mutations by Use Case

Mutations can also be split into controllers by domain. Example:

~~~java
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
    public Book registerBook(
            @Argument("input") RegisterBookInput input) {
        return bookService.register(input);
    }
}
~~~

Another controller can handle renaming an author:

~~~java
@Controller
public class AuthorMutationController {

    private final AuthorService authorService;

    public AuthorMutationController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @MutationMapping
    public Author renameAuthor(
            @Argument("id") String id,
            @Argument("name") String name) {
        return authorService.rename(id, name);
    }
}
~~~

`RegisterBookInput` can be a DTO or record:

~~~java
public record RegisterBookInput(String title, String authorId) {
}
~~~

Controllers call application services to execute business logic. Do not call methods on other controllers directly or place shared business logic inside controllers. If multiple resolvers need the same behavior, move that behavior into a service or an appropriate application component.

## A GraphQL Field Should Have Only One Mapping

Spring for GraphQL must identify a unique resolver for each mapped field. If two controllers both register a mapping for `Query.bookById`, the application may fail with an ambiguous mapping error when initializing GraphQL handlers.

For example, do not create these two methods in two different controllers:

~~~java
@Controller
class FirstBookController {
    @QueryMapping
    Book bookById(@Argument("id") String id) {
        // ...
    }
}

@Controller
class SecondBookController {
    @QueryMapping
    Book bookById(@Argument("id") String id) {
        // ...
    }
}
~~~

Both methods target the `Query.bookById` field. GraphQL does not pick a controller based on package, class name, or component scan order.

If two different use cases need to look up books, choose one of these approaches:

- Create separate GraphQL fields with clear names and semantics.
- Keep a single resolver and delegate to the appropriate services or strategies.
- Extract shared logic into a service, while letting only one method register the mapping for that field.

Do not use multiple controllers to create competing resolver versions for the same field. A single mapping keeps the schema and execution flow predictable.

## What Criteria Should Guide Splitting Controllers?

There is no single structure that fits every application. You can choose how to split based on schema size, business boundaries, and how teams own the code.

| Splitting Approach | When Appropriate | Example |
| --- | --- | --- |
| By root operation | Queries and mutations have many fields, requiring separation of read/write responsibilities | BookQueryController, BookMutationController |
| By object type | Many nested fields on one type need custom logic | BookFieldController, OrderFieldController |
| By business domain | Large schema with multiple teams owning independent domains | catalog, sales, identity |
| By use case | One domain has distinct operation groups with clear boundaries | BookSearchController, BookAdministrationController |

Some practical principles:

- Keep each controller focused on a related group of mappings.
- Avoid a giant controller containing every field of the entire schema.
- Avoid creating one controller per trivial field if doing so over-fragments the codebase.
- Let services own business logic, transactions, and data access.
- Keep GraphQL field names stable even when Java class or package names change.
- Organize packages by business domain so component scanning and code ownership stay clear.

## Execution Flow When Multiple Controllers Participate

One operation can pass through multiple resolvers across multiple controllers:

~~~mermaid
flowchart TD
    A[Client sends BookDetails] --> B[GraphQL endpoint]
    B --> C[GraphQL schema and runtime]
    C --> D[BookQueryController.bookById]
    D --> E[BookService]
    E --> F[Return Book]
    F --> G[BookFieldController.author]
    G --> H[AuthorService]
    H --> I[Return Author]
    I --> J[Property data fetcher reads Author.name]
    J --> K[Assemble GraphQL response]
~~~

Each resolver only supplies data for the field it owns. The GraphQL runtime coordinates the execution order according to the operation and selection set. Clients do not need to know whether fields are handled by one controller or many controllers.

Splitting controllers also does not automatically solve performance issues. If `BookFieldController.author` queries the database once for each book in a list, the query can hit an N+1 problem. When needed, consider `@BatchMapping`, DataLoader, or batch query strategies. Multiple controllers still share those resolver optimization mechanisms.

## Security and Error Handling Do Not Depend on Controller Count

Splitting controllers does not create automatic security boundaries. All mappings still belong to the same GraphQL schema and the same endpoint. If a field contains sensitive data, enforce permissions in the resolver, via method security, or in the service so that every access path is protected.

For example, `BookFieldController` can return `Book.internalNotes` only when the user has the appropriate permission. Moving a resolver to another controller does not make a field private. Similarly, validation, exception handling, and transactions should be organized at the layers suited to their responsibilities.

## Testing Multiple Controllers on One Schema

`GraphQlTester` tests operations through the GraphQL runtime without requiring the client to know which controller holds which resolver. For example, a query can test both a root field and a nested field:

~~~java
graphQlTester.document("""
        query BookDetails($id: ID!) {
            bookById(id: $id) {
                id
                title
                author {
                    id
                    name
                }
            }
        }
        """)
    .variable("id", "book-101")
    .execute()
    .path("bookById.author.name")
    .entity(String.class)
    .isEqualTo("Nguyen An");
~~~

This test verifies that the operation passes through the `bookById` resolver, continues resolving `Book.author`, and reads `Author.name`. In slice tests with `@GraphQlTest`, include the relevant controllers in the test context and mock dependent services. Integration tests using the full application context can verify component scanning and that all controller beans are registered.

Include the following tests:

1. All required controllers are discovered by Spring.
2. Each field is mapped to exactly one resolver.
3. Root fields from different controllers work together in one schema.
4. Nested fields receive the expected source object.
5. Operations combining fields from multiple controllers return the right response.
6. Duplicate field mappings fail the test context so errors are caught early.
7. Access permissions and business errors are still handled properly when resolvers are split across classes.

## Common Errors

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| Controller is never invoked | Class lies outside component scan or is missing `@Controller` | Check package and application context |
| Field cannot find resolver | Field name or `typeName` does not match schema | Check SDL and annotation mapping |
| Application fails at startup due to mapping | Multiple methods register the same GraphQL field | Keep a single mapping per field |
| Nested field receives wrong source | Wrong source parameter or `typeName` declared | Check object type and method parameter type |
| Controllers split yet code is hard to maintain | Over-fragmented or business logic placed in controllers | Group by domain/use case and move business logic to services |
| Queries over many objects are slow | Nested resolver fetches data per item | Use batching or DataLoader when appropriate |
| Assuming a separate controller is already protected | Confusing code boundaries with authorization boundaries | Enforce permissions in services/resolvers per field |

## Comprehensive Practice

Using the library schema at the beginning of the lesson, split the resolvers into controllers:

1. `BookQueryController` handling `bookById` and `booksByAuthor`.
2. `AuthorQueryController` handling `authorById`.
3. `BookFieldController` handling `Book.author`.
4. `BookMutationController` handling `registerBook`.
5. `AuthorMutationController` handling `renameAuthor`.

Place the controllers under packages scanned by Spring Boot component scanning. Each controller injects its corresponding service via constructor. Then:

- Send a query fetching a book together with its author to verify multiple controllers participate in one operation.
- Send a mutation creating a book and verify the returned object.
- Try declaring a duplicate mapping for `Query.bookById` to observe the mapping registration error.
- Verify that services remain the place where business logic and access checks are performed.
- If a list query triggers multiple calls to fetch authors, try switching the resolver to a batch mechanism in the appropriate lesson.

## Key Takeaways

A single GraphQL schema can be handled by multiple Spring `@Controller` beans. `@QueryMapping` and `@MutationMapping` map root fields; `@SchemaMapping` maps fields on object types. Spring discovers controllers via component scanning and registers mappings by GraphQL type and field name. You can split controllers by root operation, object type, business domain, or use case, but each field should have only one mapping. Controllers coordinate services; the schema, endpoint, security, and API contract continue to be managed at the application level.
