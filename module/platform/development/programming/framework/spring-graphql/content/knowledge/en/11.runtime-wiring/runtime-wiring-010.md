# Code registry

In GraphQL Java, **CodeRegistry** is the component that links fields in the schema with execution logic. The SDL schema describes what types and fields the API exposes; the code registry tells GraphQL which `DataFetcher` to invoke to obtain a field's value and which `TypeResolver` to use to determine the actual object type when a field returns an interface or union.

In Spring for GraphQL, most applications do not need to create `GraphQLCodeRegistry` manually. Spring connects controller annotations such as `@QueryMapping` and `@SchemaMapping` to the GraphQL runtime. When you need to register a `DataFetcher`, `TypeResolver`, or execution configuration at the GraphQL Java level, you can use `RuntimeWiringConfigurer`. Understanding the relationship between the schema, `RuntimeWiring`, and `CodeRegistry` helps avoid duplicate resolver registrations and diagnose wiring errors.

## 1. What is CodeRegistry?

A GraphQL schema defines the types and fields that clients can query. Example:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
~~~

The schema states that the `Query.book` field accepts an `id` argument and returns a `Book`. However, SDL does not contain Java code to find the book. GraphQL needs a component that executes that field.

The code registry stores execution links, notably:

- **DataFetcher**: retrieves or computes the value for a field.
- **TypeResolver**: determines the concrete object type for an interface or union.

One way to visualize this:

~~~mermaid
flowchart TD
    A["GraphQL SDL"] --> B["GraphQL schema"]
    C["RuntimeWiring"] --> D["GraphQLCodeRegistry"]
    B --> E["Executable GraphQL runtime"]
    D --> E
    E --> F["Client sends operation"]
    F --> G["Look up DataFetcher by field"]
    G --> H["Execute and build response"]
~~~

The schema and code registry have distinct responsibilities:

| Component | Responsibility |
| --- | --- |
| SDL / `GraphQLSchema` | Describes the API structure and contract. |
| `RuntimeWiring` | Configures execution components when building the schema. |
| `GraphQLCodeRegistry` | Stores `DataFetcher` and `TypeResolver` mappings used by the GraphQL engine. |
| `DataFetcher` | Retrieves the value of a specific field. |
| `TypeResolver` | Selects the concrete object type for an interface or union. |

The code registry does not replace the schema. Registering a `DataFetcher` for a field not present in the schema does not expose that field to clients. Fields must still be declared in the SDL.

## 2. FieldCoordinates: the address of a field

A field is identified by its parent type and field name. GraphQL Java represents this pair with `FieldCoordinates`.

Example:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
~~~

The two fields have different coordinates:

- `Query.book`
- `Book.title`

Even when multiple types have fields with the same name, each mapping is distinguished by its parent type. Therefore, a bare field name like `book` or `id` alone is not enough to identify a unique `DataFetcher` in the schema.

In GraphQL Java, create coordinates using:

~~~java
FieldCoordinates.coordinates("Query", "book")
~~~

These coordinates specify that the `DataFetcher` will be used when GraphQL resolves the `book` field on the `Query` type.

When diagnosing mapping issues, check both the type name and field name. A `DataFetcher` registered on `Book.author` will not handle `Query.author`, even though both fields share the same name.

## 3. What is a DataFetcher?

A `DataFetcher` is the function GraphQL Java invokes to fetch the value of a field. It receives `DataFetchingEnvironment`, which supplies information about the current execution, such as:

- The source object of the field being resolved.
- Arguments passed by the client to the field.
- The GraphQL context and local context.
- Relevant field, selection, and schema information.
- Operation variables and metadata.

Example schema:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Java `DataFetcher`:

~~~java
DataFetcher<Book> bookFetcher = environment -> {
    String id = environment.getArgument("id");
    return bookService.findById(id);
};
~~~

GraphQL passes the `id` argument into the environment. The `DataFetcher` reads that value, calls the service, and returns `Book`. The GraphQL engine continues resolving child fields selected by the client, such as `id` and `title`.

A `DataFetcher` can return synchronous values or asynchronous types supported by GraphQL Java, such as `CompletionStage`. For remote service calls or I/O operations, appropriate asynchronous handling can avoid blocking request-handling threads.

Do not place all business logic inside a `DataFetcher`. Keep `DataFetcher`s focused on connecting GraphQL to services; business rules, transactions, and data access should be organized in dedicated components.

## 4. Source object and arguments in DataFetcher

`DataFetcher`s are not only for root `Query` fields. When GraphQL resolves a nested field, the source object is the result of the parent field.

Schema:

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

When a client sends:

~~~graphql
query {
    book(id: "book-42") {
        title
        author {
            name
        }
    }
}
~~~

GraphQL executes `Query.book` first. The returned `Book` value becomes the source object when resolving `Book.title` and `Book.author`. For `Book.author`, the `DataFetcher` can retrieve `authorId` from the `Book` source object and then look up `Author`.

Example `DataFetcher` for a nested field:

~~~java
DataFetcher<Author> authorFetcher = environment -> {
    Book sourceBook = environment.getSource();
    return authorService.findById(sourceBook.authorId());
};
~~~

If the field has arguments, they can also be read via `environment.getArgument`:

~~~graphql
type Book {
    reviews(first: Int = 10): [Review!]!
}
~~~

~~~java
DataFetcher<List<Review>> reviewsFetcher = environment -> {
    Book sourceBook = environment.getSource();
    Integer first = environment.getArgument("first");
    return reviewService.findByBookId(sourceBook.id(), first);
};
~~~

The source object and arguments are two distinct data sources: the source comes from the parent field, while arguments come from the current field in the operation.

## 5. RuntimeWiring connects DataFetchers with the schema

GraphQL Java provides `RuntimeWiring` as a high-level API for registering `DataFetcher`s, `TypeResolver`s, custom scalars, and other execution components. When creating an executable schema from SDL, `SchemaGenerator` uses `RuntimeWiring` to build the schema and corresponding code registry.

Example registering a `DataFetcher` for `Query.book`:

~~~java
RuntimeWiring runtimeWiring = RuntimeWiring.newRuntimeWiring()
    .type("Query", typeWiring -> typeWiring
        .dataFetcher("book", environment -> {
            String id = environment.getArgument("id");
            return bookService.findById(id);
        }))
    .build();
~~~

In this example:

- `type("Query", ...)` selects the object type named `Query`.
- `dataFetcher("book", ...)` registers the `DataFetcher` for `Query.book`.
- `environment.getArgument("id")` reads the argument processed by GraphQL.
- The result from the service becomes the value of the `book` field.

`SchemaGenerator` uses `TypeDefinitionRegistry` and `RuntimeWiring` to produce a `GraphQLSchema`:

~~~java
TypeDefinitionRegistry typeRegistry =
        new SchemaParser().parse(schemaFile);

GraphQLSchema schema = new SchemaGenerator()
        .makeExecutableSchema(typeRegistry, runtimeWiring);
~~~

This is how a schema is built at the raw GraphQL Java level. In Spring Boot applications, Spring for GraphQL normally manages loading SDL and building the GraphQL runtime. Therefore, you do not need to manually instantiate `SchemaParser` or `SchemaGenerator` in each controller.

## 6. GraphQLCodeRegistry and direct registration

`GraphQLCodeRegistry` is the execution registry attached to `GraphQLSchema`. You can create a builder and register a `DataFetcher` using `FieldCoordinates`:

~~~java
DataFetcher<Book> bookFetcher =
        environment -> bookService.findById(
                environment.getArgument("id"));

GraphQLCodeRegistry codeRegistry =
        GraphQLCodeRegistry.newCodeRegistry()
            .dataFetcher(
                FieldCoordinates.coordinates("Query", "book"),
                bookFetcher
            )
            .build();
~~~

During schema construction at the GraphQL Java level, the registry is attached to `GraphQLSchema`:

~~~java
GraphQLSchema schema = GraphQLSchema.newSchema()
        .query(queryType)
        .codeRegistry(codeRegistry)
        .build();
~~~

This example assumes `queryType` and the required types have already been constructed validly. In real applications, `GraphQLSchema` must contain all required types, root operations, and mappings.

When using GraphQL Java directly, `GraphQLCodeRegistry` is useful if you need explicit control over mappings by `FieldCoordinates`. In Spring Boot applications, you should usually register via `RuntimeWiringConfigurer` to integrate with the Spring-managed `GraphQlSource`, rather than building a standalone `GraphQLSchema` and bypassing auto-configuration.

## 7. Registering RuntimeWiringConfigurer in Spring for GraphQL

Spring for GraphQL allows applications to provide `RuntimeWiringConfigurer` beans. Spring invokes configurers when building the GraphQL runtime from SDL.

Example:

~~~java
package com.example.catalog.config;

import com.example.catalog.book.BookService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlConfig {

    @Bean
    RuntimeWiringConfigurer bookRuntimeWiring(BookService bookService) {
        return wiringBuilder -> wiringBuilder
            .type("Query", typeWiring -> typeWiring
                .dataFetcher("book", environment -> {
                    String id = environment.getArgument("id");
                    return bookService.findById(id);
                }));
    }
}
~~~

Corresponding schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
~~~

Spring Boot manages the configurer bean and merges its configuration when building the GraphQL runtime. The registered `DataFetcher` will handle `Query.book` when clients query that field.

An application can have multiple `RuntimeWiringConfigurer` beans, each contributing part of the configuration. Splitting by domain or feature is helpful when it keeps code manageable, while avoiding multiple configurers registering the same field coordinates.

### Do not duplicate registrations with controller annotations

Spring for GraphQL supports annotated controllers:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
~~~

`@QueryMapping` is discovered by Spring and registered as the `DataFetcher` for `Query.book`. Therefore, if `Query.book` is already handled by this controller, do not register another `DataFetcher` for the same coordinates in `RuntimeWiringConfigurer`.

Choose one owner responsible for each mapping:

- Use `@QueryMapping`, `@MutationMapping`, and `@SchemaMapping` for logic tied to Spring controllers.
- Use `RuntimeWiringConfigurer` when you need direct GraphQL Java API integration, such as custom `DataFetcher`s or `TypeResolver`s.
- Rely on the default property data fetcher when a field can be read directly from a property of the source object.

Registering duplicate mappings can cause conflicts or unpredictable behavior depending on how configurers are combined. Keep a single clear mapping source for every field.

## 8. TypeResolver in CodeRegistry

`DataFetcher` retrieves a field's value. `TypeResolver` solves a different problem: when a field returns an interface or union, GraphQL needs to know which concrete type the actual object belongs to in order to select the right selection set.

Example schema:

~~~graphql
interface SearchResult {
    id: ID!
}

type Book implements SearchResult {
    id: ID!
    title: String!
}

type Author implements SearchResult {
    id: ID!
    name: String!
}

type Query {
    search(keyword: String!): [SearchResult!]!
}
~~~

The `Query.search` resolver can return a list of `Book` and `Author` objects. However, GraphQL needs a `TypeResolver` to determine the concrete type of each element.

Example configuration in `RuntimeWiring`:

~~~java
.type("SearchResult", typeWiring -> typeWiring
    .typeResolver(environment -> {
        Object source = environment.getObject();

        if (source instanceof Book) {
            return environment.getSchema().getObjectType("Book");
        }

        if (source instanceof Author) {
            return environment.getSchema().getObjectType("Author");
        }

        return null;
    }))
~~~

In real applications, ensure every concrete type that might appear is handled. If the resolver cannot determine the type, GraphQL cannot complete the interface/union field and will produce an execution error.

For unions, the same rule applies: `TypeResolver` must return an object type that is a valid member of the union. It cannot return a type not declared in the union or an input type.

## 9. CodeRegistry and the default property data fetcher

Not every field requires a custom `DataFetcher`. GraphQL Java has a property data fetching mechanism to read values from the source object.

Example:

~~~graphql
type Book {
    id: ID!
    title: String!
}
~~~

If `Query.book` returns a Java `Book` object with appropriate accessors for `id` and `title`, GraphQL can read those values without registering separate `DataFetcher`s for `Book.id` and `Book.title`.

Java record example:

~~~java
public record Book(String id, String title) {
}
~~~

With this record, the `id()` and `title()` accessors supply the corresponding data. With JavaBeans, getters such as `getId()` and `getTitle()` are typically used by the property data fetcher.

When you need to query relationships or compute fields, register a dedicated `DataFetcher`:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author
}
~~~

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.authorId());
}
~~~

Property access fits when the data already exists on the source object. Custom resolvers fit when a field needs a service, repository, arguments, or business logic. Avoid adding explicit mappings merely to repeat the exact same value the property fetcher already supplies.

## 10. Custom scalars and related wiring components

The code registry focuses on `DataFetcher` and `TypeResolver`. `RuntimeWiring` can also register other components such as custom scalars.

Example SDL:

~~~graphql
scalar DateTime

type Event {
    id: ID!
    startsAt: DateTime!
}
~~~

If `DateTime` is a custom scalar, the application must provide a `GraphQLScalarType` implementation with appropriate input-parsing and output-serialization rules. It can be registered via `RuntimeWiringConfigurer`:

~~~java
@Bean
RuntimeWiringConfigurer scalarConfigurer(GraphQLScalarType dateTimeScalar) {
    return wiringBuilder -> wiringBuilder.scalar(dateTimeScalar);
}
~~~

A custom scalar is not a `DataFetcher`. A scalar defines how values are converted; a `DataFetcher` retrieves a field's value. Even though both are configured via `RuntimeWiring`, these two responsibilities are distinct.

Similarly, directive wiring or type resolvers each have their own responsibilities. When debugging, identify which component is missing before adding new configuration to the registry.

## 11. Testing mappings and code registry

You can use `GraphQlTester` to verify that fields are registered and return the right data:

~~~java
@Test
void resolvesBookThroughGraphQl() {
    graphQlTester.document("""
            query BookDetail($id: ID!) {
                book(id: $id) {
                    id
                    title
                }
            }
            """)
        .variable("id", "book-42")
        .execute()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring in Action");
}
~~~

When using `RuntimeWiringConfigurer`, test that operations invoke the expected `DataFetcher`. You can mock or spy on the service to verify that:

- `DataFetcher` receives the expected arguments.
- `DataFetcher` calls the service once with the corresponding key.
- Fields are not invoked when omitted from the selection set.
- Nested fields receive the expected source object.
- `TypeResolver` returns the right concrete type for each object.
- Custom scalars parse and serialize according to the published format.

Include integration tests that build the GraphQL runtime from the real SDL. A test that only invokes a `DataFetcher` lambda directly does not confirm that the mapping is attached to the right coordinates or that the schema loaded properly.

## 12. Common mistakes when configuring CodeRegistry

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Field exists in SDL but returns no data | No matching `DataFetcher` and source object lacks the corresponding property. | Register a `DataFetcher` or provide the proper property/accessor. |
| `DataFetcher` is never called | Mapping registered under the wrong type name or field name. | Check `FieldCoordinates` or `type` in `RuntimeWiring`. |
| Field unexpectedly returns null | Source object lacks a value, service returns null, or property fetcher cannot find accessor. | Check source, getter/record accessor, and service. |
| Controller mapping conflicts | Same field registered via both annotations and `RuntimeWiringConfigurer`. | Keep only one mapping for those field coordinates. |
| Interface/union fails to resolve | Missing `TypeResolver` or resolver does not recognize the object. | Register `TypeResolver` and handle all valid concrete types. |
| Custom scalar does not work | `GraphQLScalarType` not registered or coercing is incorrect. | Configure the scalar via `RuntimeWiringConfigurer`. |
| Query calls service too many times | Child `DataFetcher` runs a separate query per source object. | Measure call counts and use DataLoader or `@BatchMapping` where appropriate. |
| Schema startup failure | SDL or schema validation error mistaken for a registry error. | Check parsing/validation first, then check wiring. |

When a `DataFetcher` does not run, inspect the schema first, then check mapping coordinates and whether Spring registered the configurer. If the field runs but returns null, inspect the source object and service. If errors occur only on interfaces or unions, focus on `TypeResolver`.

## 13. Key points to remember

- `GraphQLCodeRegistry` stores `DataFetcher` and `TypeResolver` mappings used by the GraphQL runtime.
- `FieldCoordinates` identifies a field by its parent type and field name pair.
- `DataFetcher` retrieves field values from the source object, arguments, and context.
- `RuntimeWiring` is the high-level API for configuring execution components when creating the schema; the code registry is embedded into `GraphQLSchema`.
- Spring for GraphQL lets you add configuration via `RuntimeWiringConfigurer`.
- `@QueryMapping` and `@SchemaMapping` are also converted into `DataFetcher`s by Spring; avoid registering duplicates for the same field.
- The default property data fetcher can read accessors from the source object without a custom resolver.
- `TypeResolver` determines concrete object types for interfaces and unions.
- Custom scalars are a separate wiring component, not `DataFetcher`s.
- When diagnosing issues, check the SDL, `FieldCoordinates`, configurers, source objects, and the corresponding resolver type.

`CodeRegistry` is the bridge between schema structure and execution logic in GraphQL Java. In Spring for GraphQL, understanding the registry alongside `RuntimeWiringConfigurer` helps integrate custom resolvers cleanly, keep mappings clear, and handle complex data types without cluttering controller structure.

