# Java Object as GraphQL Result

In Spring for GraphQL, a resolver can return a Java object so that the GraphQL runtime produces the result for an object type in the schema. For example, a `book(id: ...)` query can return a `BookView` object; the client then selects `id`, `title`, `author`, or other fields of that object.

The key point to understand is that a Java object is not returned directly as a fixed JSON block. The GraphQL runtime reads the client's selection set and resolves each field on the source object. Fields can be read from Java properties via the default mechanism, or use a dedicated resolver with `@SchemaMapping` when data querying, computation, or authorization checks are needed.

## 1. Java objects and GraphQL object types

GraphQL SDL defines the output data structure. For example:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    description: String
    publishedYear: Int
}
```

`Query.book` returns a `Book` or `null`. If the book is found, the resolver can return a Java object carrying the corresponding data. `Book` in SDL is the API contract; the Java class is an internal data representation used to provide results for that contract.

The Java class name does not have to match the GraphQL type name. However, GraphQL fields need a corresponding way to resolve. For fields handled by default, Java property names typically need to match the field names in SDL. For fields with different names or data sources, explicit resolvers can be declared.

## 2. Returning a Java object from @QueryMapping

Example of a simple JavaBean DTO:

```java
package com.example.graphql.book;

public class BookView {

    private final String id;
    private final String title;
    private final String description;
    private final Integer publishedYear;
    private final String authorId;

    public BookView(
            String id,
            String title,
            String description,
            Integer publishedYear,
            String authorId) {
        this.id = id;
        this.title = title;
        this.description = description;
        this.publishedYear = publishedYear;
        this.authorId = authorId;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getDescription() {
        return description;
    }

    public Integer getPublishedYear() {
        return publishedYear;
    }

    public String getAuthorId() {
        return authorId;
    }
}
```

Controller returning the object:

```java
package com.example.graphql.book;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public BookView book(@Argument("id") String id) {
        return bookService.findViewById(id);
    }
}
```

The `book` method is mapped to `Query.book`. The return value is a `BookView`; the GraphQL runtime continues resolving the fields that the client selected on this object.

## 3. PropertyDataFetcher reading Java properties

For a field without a custom resolver, GraphQL Java typically uses the default property data fetcher (`PropertyDataFetcher`) to read the value from the source object. For a JavaBean, this mechanism can read through getters such as `getTitle()` or `isAvailable()`; for a `Map`, the value can be retrieved by the key matching the field name.

For example, the client sends:

```graphql
query BookSummary($id: ID!) {
    book(id: $id) {
        id
        title
        publishedYear
    }
}
```

When `BookView` is the source object:

- The GraphQL field `id` is resolved from the `id` property.
- The GraphQL field `title` is resolved from the `title` property.
- The GraphQL field `publishedYear` is resolved from the `publishedYear` property.

There is no need to write three `@SchemaMapping` methods just to return values that already exist on the DTO. The default resolver reduces boilerplate code and keeps simple fields easy to read.

Field names must be compatible with property access. If the Java model uses `bookName` while the schema exposes `title`, the property fetcher will not automatically know that these two names have the same meaning. Use a DTO with matching property names or declare an explicit mapping.

## 4. Fields with different names or custom logic

When a GraphQL field cannot be read directly from the source object, use `@SchemaMapping` to provide a resolver.

For example, `BookEntity` only stores `authorId`, while the schema wants to return an `Author` object:

```graphql
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
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public AuthorView author(BookView book) {
        return authorService.findViewById(book.getAuthorId());
    }
}
```

`@SchemaMapping` connects the `Book.author` field to the `author` method; the method receives the parent object as the source and returns an `AuthorView` Java object for the child field.

Method-level mapping can be used when a field needs to call a service, combine multiple data sources, apply authorization rules, or transform data. You do not need to write resolvers for every property if the default property fetcher already satisfies the requirement.

## 5. Nested objects and selection sets

A Java object can contain another object. Example DTO:

```java
public class BookView {
    private String id;
    private String title;
    private AuthorView author;

    public String getId() { return id; }
    public String getTitle() { return title; }
    public AuthorView getAuthor() { return author; }
}

public class AuthorView {
    private String id;
    private String name;

    public String getId() { return id; }
    public String getName() { return name; }
}
```

If `BookView.author` already contains `AuthorView`, GraphQL can resolve nested fields using the default property fetcher:

```graphql
query {
    book(id: "book-42") {
        title
        author {
            id
            name
        }
    }
}
```

The runtime resolves `Query.book` first, then resolves `Book.title` and `Book.author`. For the `AuthorView` object, it continues resolving `Author.id` and `Author.name` according to the selection set.

If `author` is not yet available on the parent object, use `@SchemaMapping` as in the previous section. Whether the nested object is retrieved from a DTO or a separate resolver, the returned data type must be compatible with the declared GraphQL type.

## 6. Returning Java collections

A GraphQL list is typically provided as a Java collection such as `List<T>`, or an iterable/array type supported by GraphQL Java. For example:

```graphql
type Query {
    booksByAuthor(authorId: ID!): [Book!]!
}
```

Resolver:

```java
@QueryMapping
public List<BookView> booksByAuthor(@Argument("authorId") String authorId) {
    return bookService.findViewsByAuthorId(authorId);
}
```

The client selects fields of each element:

```graphql
query {
    booksByAuthor(authorId: "author-7") {
        id
        title
    }
}
```

The type `[Book!]!` promises that the list is non-null and each element is non-null. An empty list `[]` is still a valid result. If the Java collection contains a null element, the result violates element nullability and GraphQL may produce an execution error along with null propagation.

For large lists, design pagination and limit the number of elements. Returning an unbounded collection can increase memory usage, query execution time, and response size.

## 7. Java Map as GraphQL result

In some cases, a resolver can return `Map<String, Object>` instead of a DTO. The property fetcher can read values by keys corresponding to GraphQL fields.

For example:

```java
@QueryMapping
public Map<String, Object> dashboard() {
    return Map.of(
        "activeUsers", 125,
        "openOrders", 18,
        "status", "HEALTHY"
    );
}
```

Corresponding SDL:

```graphql
type Query {
    dashboard: Dashboard!
}

type Dashboard {
    activeUsers: Int!
    openOrders: Int!
    status: String!
}
```

The keys in the map must correspond to the fields exposed by the schema. If a key is missing or the value has the wrong type, the field may return null or cause a coercion/nullability error depending on the case.

Maps are flexible and useful for aggregated results or dynamic structures. However, DTOs are usually easier to maintain for stable contracts because the compiler can assist with type checking and IDEs can navigate properties. Do not use maps indiscriminately for all domain objects because typos in key names only surface when the query is executed.

## 8. Java types and GraphQL scalars

Scalar properties in Java need appropriate coercion compatible with the scalars in SDL.

| GraphQL scalar | Common Java type | Notes |
| --- | --- | --- |
| `String` | `String` | Does not automatically convert arbitrary objects into API strings |
| `Boolean` | `Boolean` or `boolean` | Wrapper `Boolean` can be null; primitive cannot be null |
| `Int` | `Integer` or `int` | GraphQL `Int` is a signed 32-bit integer |
| `Float` | `Double`, `Float`, or supported numeric types | Clarify precision and conversion rules |
| `ID` | Usually `String` | Used for identifiers, not arithmetic |
| `enum` | Corresponding Java `enum` | Names/values must be mapped appropriately |

Dates, timestamps, currency, or special domain types often require a custom scalar or an explicit API representation. For example, `LocalDate` does not automatically become a built-in GraphQL scalar in every configuration; the application needs to register a scalar with appropriate coercing or convert it to a string in an agreed format.

Do not assume that the Jackson JSON serializer determines the entire GraphQL field mapping. The GraphQL runtime uses the schema, data fetchers, and scalar coercing to resolve and serialize each field according to the GraphQL contract.

## 9. Nullability between Java and GraphQL

Java and GraphQL represent nullability differently. In SDL, the `!` mark is an API promise:

```graphql
type Book {
    id: ID!
    title: String!
    description: String
}
```

A Java `String` can be null even if the GraphQL field is declared `String!`. If the getter returns null for `title`, GraphQL produces an execution error and propagates null up to the nearest nullable parent field. Therefore, ensure the DTO satisfies the schema's non-null contract.

For Java primitives like `int` or `boolean`, values cannot be null and may fit when the API always has a default value. However, primitives can hide the difference between "no data" and a default value like `0` or `false`. Use wrapper types `Integer` or `Boolean` when null is a meaningful state and SDL allows it.

For example:

| Java property | SDL | Meaning |
| --- | --- | --- |
| `String title` | `title: String!` | Getter must always return a non-null string |
| `String description` | `description: String` | May return null |
| `Integer publishedYear` | `publishedYear: Int` | Publication year may not be available yet |
| `int pageCount` | `pageCount: Int!` | Always has an integer value |

The schema should reflect actual data capabilities and business rules; do not add `!` just to make the response look complete.

## 10. DTO or JPA entity as GraphQL result?

You can return a JPA entity directly if the entity's structure and lifecycle fit the API. However, for applications with complex domain models, DTOs generally help control the GraphQL contract better.

| Criterion | Returning JPA entity | Returning DTO/View model |
| --- | --- | --- |
| Initial implementation speed | Can be fast when structures are simple | Requires a mapping step |
| Control over exposed fields | Easy to accidentally depend on the entity | Explicitly selects fields to expose |
| Lazy loading | Can trigger queries while resolving fields | Can prepare data per use case |
| Cyclic relationships | Can lead to deep selections or hard-to-control logic | Can intentionally shape the response |
| Separation of domain and API | Couples API contract to persistence model | API is more independent of database schema |

DTOs do not automatically solve N+1. If a service builds a DTO by loading each relationship individually, the problem still exists. Use projections, fetch plans, batch loading, or DataLoader based on query needs.

In particular, do not return entities containing sensitive attributes just because current clients do not select them yet. Only fields declared in the schema can be queried by clients, but as the schema expands, the property fetcher can expose data if an entity is used directly without reviewing authorization and new fields.

## 11. Interfaces and Unions when Java results have multiple concrete types

A GraphQL field can return an interface or union, while the Java resolver returns objects of different classes.

Example SDL:

```graphql
interface SearchResult {
    id: ID!
    title: String!
}

type Book implements SearchResult {
    id: ID!
    title: String!
    author: String!
}

type Article implements SearchResult {
    id: ID!
    title: String!
    source: String!
}

type Query {
    search(keyword: String!): [SearchResult!]!
}
```

The resolver can return a list containing `BookView` and `ArticleView`, but the GraphQL runtime needs to know the concrete object type of each element. In that case, configure appropriate type resolution, such as a `TypeResolver` via `RuntimeWiringConfigurer`, to map Java implementations to GraphQL object types.

```java
@Bean
RuntimeWiringConfigurer searchResultTypeResolver() {
    return builder -> builder.type("SearchResult", wiring ->
        wiring.typeResolver(environment -> {
            Object source = environment.getObject();
            if (source instanceof BookView) {
                return environment.getSchema().getObjectType("Book");
            }
            if (source instanceof ArticleView) {
                return environment.getSchema().getObjectType("Article");
            }
            throw new IllegalStateException("Unsupported search result type");
        })
    );
}
```

The example above illustrates the mapping principle. In real code, explicitly handle null sources and ensure every implementation that can appear is registered. If returning only a single concrete object type like `Book`, a polymorphic type resolver is not needed.

## 12. Asynchronous object results

A resolver can return an object directly or an asynchronous type supported by Spring for GraphQL. For example:

```java
@QueryMapping
public CompletableFuture<BookView> book(@Argument("id") String id) {
    return bookService.findViewByIdAsync(id);
}
```

For reactive applications, a method can return `Mono<BookView>` when using the corresponding stack and dependencies. Whether the result is provided synchronously or asynchronously, once the object is available, GraphQL resolves the fields according to the selection set as usual.

Do not wrap a blocking call in `CompletableFuture` just to make the method look asynchronous. Consider thread pools, actual I/O, and how the service accesses data. The wrapper type does not change the GraphQL object type contract it represents.

## 13. Testing Java objects as GraphQL results

`GraphQlTester` allows executing queries and verifying fields read from Java objects:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest(BookQueryController.class)
class BookQueryControllerTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void mapsJavaObjectPropertiesToGraphQlFields() {
        graphQlTester.document("""
                query {
                    book(id: "book-42") {
                        id
                        title
                    }
                }
                """)
            .execute()
            .path("book.title")
            .entity(String.class)
            .isEqualTo("Practical Spring GraphQL");
    }
}
```

The example assumes the test context provides a mock `BookService` or test bean returning a `BookView` with ID `book-42` and the expected title. This test verifies both the root mapping and GraphQL reading properties from the Java object.

You should add tests for:

- JavaBean fields resolved via getters.
- Non-existent properties or names not matching the schema.
- Nested objects and collections.
- Null in nullable fields and violations of non-null fields.
- Map results with corresponding keys.
- Custom scalars and enum coercion.
- Interfaces/unions with each concrete implementation.
- Asynchronous resolvers and errors raised when completing a future/publisher.

In integration tests, also verify database projections, lazy loading, security, and transactions to see whether the returned object meets both the contract and performance expectations.

## 14. Common errors when returning Java objects

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Field returns null even though object has data | Getter or property name does not match field | Check accessors and use `@SchemaMapping` when needed |
| Object field cannot be queried | Client is missing selection set | Select child fields in the query |
| Non-null execution error | Java property returns null while SDL declares `!` | Fix data or adjust nullability to match business rules |
| Scalar coercion error | Java type incompatible with scalar | Use compatible type or custom scalar |
| Nested field triggers many queries | Lazy loading or per-parent resolver | Use projection, `@BatchMapping`, or DataLoader |
| Map missing key | Key name does not match field or incomplete data | Standardize keys or use a typed DTO |
| Interface cannot resolve | Concrete GraphQL type not determined | Register appropriate `TypeResolver` or `isTypeOf` |
| API exposes unintended fields when schema expands | Returning entity directly without reviewing properties | Use DTOs and control fields/authorization |

## 15. Checklist for designing Java result types

- Does the Java object provide enough data for the GraphQL object type?
- Are property names and accessors compatible with fields in SDL?
- Do fields requiring custom logic have appropriate `@SchemaMapping`?
- Do nested objects and collections have nullability matching the schema?
- Do Java types have coercion compatible with scalars and enums?
- Was the choice between DTO and entity made based on API boundaries, authorization, and persistence?
- Is there a risk of lazy loading or N+1 when resolving child fields?
- Do interfaces/unions have a type resolver for every implementation?
- Do asynchronous types reflect actual I/O and are they supported by the current stack?
- Do tests verify responses, nullability, and coercion errors?

Using a Java object as a GraphQL result is a common way to connect a Spring application's data with object types in the schema. `@QueryMapping` or `@SchemaMapping` returns the source object; the GraphQL runtime reads the selection set and resolves each field using the default property fetcher or a custom data fetcher. Choosing DTOs with clear accessors, designing accurate nullability, handling nested objects intentionally, and controlling data queries keeps the API maintainable, safe, and stable in performance.
