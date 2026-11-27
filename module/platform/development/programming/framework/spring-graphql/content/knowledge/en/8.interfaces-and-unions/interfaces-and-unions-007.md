# Union Mapping in Controllers with Spring for GraphQL

## Objectives

After this lesson, you will be able to:

- Explain how a GraphQL union represents a result that can belong to multiple object types.
- Declare a union and its member objects in SDL.
- Write operations using inline fragments to retrieve fields based on result type.
- Return different object types from a single `@QueryMapping` method.
- Understand the role of `TypeResolver` in determining the actual GraphQL object type.
- Register a union mapping using `RuntimeWiringConfigurer`.
- Use `ClassNameTypeResolver` or a custom resolver when Java class names differ from GraphQL type names.
- Test union mapping and handle cases where the server returns an undeclared type.
- Distinguish the responsibilities of controllers, resolvers, unions, and field mappings on member objects.

## 1. What Is a Union?

A GraphQL union is an abstract type that allows a field to return one of several declared object types. Unions are useful when a search result or a list can contain different kinds of objects.

For example, a catalog search feature might return books or authors:

~~~graphql
type Book {
    id: ID!
    title: String!
}

type Author {
    id: ID!
    name: String!
}

union SearchResult = Book | Author

type Query {
    searchCatalog(keyword: String!): [SearchResult!]!
}
~~~

`SearchResult` is a union consisting of two members: `Book` and `Author`. The `searchCatalog` field returns a list of results; each element can be a `Book` or an `Author`.

A union only lists object types. You cannot declare a scalar, enum, input object, interface, or another union as a member of a union. Members must be valid object types in the schema.

A union does not declare shared fields like an interface. It only describes the set of object types a result may belong to. Therefore, clients cannot directly select `id` or `title` on `SearchResult` unless those fields are defined on a shared interface.

## 2. Clients Querying Unions with Inline Fragments

Because a union has no business fields of its own, clients use inline fragments to select fields per concrete object type.

~~~graphql
query SearchCatalog {
    searchCatalog(keyword: "Spring") {
        __typename
        ... on Book {
            id
            title
        }
        ... on Author {
            id
            name
        }
    }
}
~~~

Meaning:

- `__typename` returns the actual GraphQL object type name of each element.
- `... on Book` selects only fields belonging to `Book`.
- `... on Author` selects only fields belonging to `Author`.

Example response:

~~~json
{
    "data": {
        "searchCatalog": [
            {
                "__typename": "Book",
                "id": "book-42",
                "title": "Spring GraphQL"
            },
            {
                "__typename": "Author",
                "id": "author-12",
                "name": "An Nguyen"
            }
        ]
    }
}
~~~

Clients can rely on `__typename` to decide how to render each result. For instance, a `Book` result can link to a book detail page, while `Author` links to an author profile page.

If an operation requests a field directly that does not exist on the union, GraphQL validation rejects the operation:

~~~graphql
query {
    searchCatalog(keyword: "Spring") {
        id
    }
}
~~~

`id` may exist on both `Book` and `Author`, but the `SearchResult` union does not declare that field. GraphQL does not automatically infer that all members sharing a field name form a common field. Use inline fragments or define an interface if a shared field contract is needed.

## 3. Controllers Returning Multiple Object Types

In Spring for GraphQL, a method annotated with `@QueryMapping` can return a list containing different types of Java objects. The controller focuses on receiving arguments and calling the search service.

Example result models:

~~~java
public record BookView(String id, String title) {
}

public record AuthorView(String id, String name) {
}
~~~

The service returns objects belonging to different classes:

~~~java
@Service
class CatalogSearchService {

    List<Object> search(String keyword) {
        return List.of(
                new BookView("book-42", "Spring GraphQL"),
                new AuthorView("author-12", "An Nguyen")
        );
    }
}
~~~

Controller:

~~~java
@Controller
class CatalogController {

    private final CatalogSearchService searchService;

    CatalogController(CatalogSearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    List<Object> searchCatalog(@Argument String keyword) {
        return searchService.search(keyword);
    }
}
~~~

`@QueryMapping` maps the `searchCatalog` method to the field of the same name on the `Query` root type. The return value is a list of source objects. Each source object must be resolved by the GraphQL runtime into a GraphQL object type belonging to the `SearchResult` union.

In this example, the first element is `BookView` and the second element is `AuthorView`. The Java class names differ from the GraphQL object type names, so an explicit mapping rule is needed.

You can use a shared Java interface instead of `List<Object>` to represent results belonging to the same group in the domain:

~~~java
interface CatalogSearchItem {
}

public record BookView(String id, String title)
        implements CatalogSearchItem {
}

public record AuthorView(String id, String name)
        implements CatalogSearchItem {
}
~~~

Then the controller method can return `List<CatalogSearchItem>`. The Java interface helps represent the result group in code, but it does not automatically replace the union in the GraphQL schema. The GraphQL runtime still needs to determine the concrete object type for each element.

## 4. TypeResolver Determines the Actual Object Type

GraphQL needs to know which GraphQL object type each source object in a union result corresponds to. That responsibility belongs to `TypeResolver`.

When executing a field returning a union:

1. The field resolver, such as a `@QueryMapping` method, returns an object or a list of objects.
2. The GraphQL runtime receives the source object for each element.
3. The union's `TypeResolver` inspects the source object.
4. The `TypeResolver` returns the corresponding `GraphQLObjectType`, such as `Book` or `Author`.
5. The GraphQL runtime uses that object type to execute the selection set and matching inline fragments.

`TypeResolver` does not create data or query a database. It only determines the concrete GraphQL type of a source object already returned by a resolver.

If the object type cannot be determined, GraphQL cannot complete executing the union member. Therefore, every Java type that the service can return for the union must have a valid mapping.

### 4.1. Class-Name-Based Mapping Rules

Spring for GraphQL provides `ClassNameTypeResolver` to infer the GraphQL object type from the Java class name. This approach is convenient when Java class names match the object type names in SDL.

For example, a source object of class `Book` can be mapped to the GraphQL object type `Book`. However, in real applications, Java classes often carry suffixes such as `BookView`, `BookDto`, or `BookEntity` while the schema only exposes `Book`.

When names do not match, configure explicit mappings instead of relying on implicit naming conventions.

### 4.2. Registering ClassNameTypeResolver for a Union

Example configuring mappings between Java DTOs and GraphQL object types:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.ClassNameTypeResolver;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
class GraphQlUnionConfiguration {

    @Bean
    RuntimeWiringConfigurer unionTypeResolver() {
        ClassNameTypeResolver typeResolver =
                new ClassNameTypeResolver();

        typeResolver.addMapping(BookView.class, "Book");
        typeResolver.addMapping(AuthorView.class, "Author");

        return wiringBuilder ->
                wiringBuilder.type(
                        "SearchResult",
                        typeWiring -> typeWiring.typeResolver(typeResolver)
                );
    }
}
~~~

In this configuration:

- `ClassNameTypeResolver` is a resolver supporting Java-class-based mapping.
- `addMapping(BookView.class, "Book")` explicitly specifies that source object `BookView` corresponds to GraphQL type `Book`.
- `addMapping(AuthorView.class, "Author")` maps source object `AuthorView` to GraphQL type `Author`.
- `RuntimeWiringConfigurer` registers the resolver for the abstract type named `SearchResult`.

The name `SearchResult` must match the union in SDL. The names `Book` and `Author` must match object types declared and listed in the union.

Registering explicit mappings is especially useful when using DTOs, projections, or domain classes whose names differ from GraphQL types. If using class names as a default convention, make sure that convention is stable and creates no collisions across classes.

## 5. Writing a Custom TypeResolver When Custom Rules Are Needed

`ClassNameTypeResolver` suits class-based mappings. If the application needs to decide the type based on a property or structure of the source object, you can write a `TypeResolver` directly.

For example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
class CustomUnionConfiguration {

    @Bean
    RuntimeWiringConfigurer unionTypeResolver() {
        return wiringBuilder -> wiringBuilder.type(
                "SearchResult",
                typeWiring -> typeWiring.typeResolver(environment -> {
                    Object source = environment.getObject();

                    if (source == null) {
                        throw new IllegalStateException(
                                "SearchResult source must not be null"
                        );
                    }

                    if (source instanceof BookView) {
                        return environment.getSchema()
                                .getObjectType("Book");
                    }

                    if (source instanceof AuthorView) {
                        return environment.getSchema()
                                .getObjectType("Author");
                    }

                    throw new IllegalStateException(
                            "Unsupported SearchResult source type: "
                                    + source.getClass().getName()
                    );
                })
        );
    }
}
~~~

In this example:

- `environment.getObject()` retrieves the source object being resolved by the GraphQL runtime.
- `environment.getSchema().getObjectType("Book")` looks up the `Book` object type from the current schema.
- Each branch returns the exact object type exposed by the union.
- An unsupported source type produces a clear error rather than silently picking the wrong GraphQL type.

If the source object could be null, handle that case intentionally before calling `getClass()`. Typically, when union members are declared non-null such as `[SearchResult!]!`, the service should not place null elements in the list.

Prefer `ClassNameTypeResolver` when mapping is purely class-based. Only write a custom resolver when specific classification rules are required, for example when the source object is a generic wrapper containing a discriminator that identifies the result type.

## 6. A Complete Example from SDL to Controller

Combining schema, DTOs, service, controller, and runtime wiring.

### 6.1. Schema SDL

~~~graphql
type Book {
    id: ID!
    title: String!
    publishedYear: Int
}

type Author {
    id: ID!
    name: String!
    biography: String
}

union SearchResult = Book | Author

type Query {
    searchCatalog(keyword: String!): [SearchResult!]!
}
~~~

`SearchResult` has two members. The root field `searchCatalog` returns a non-null list where every element is also non-null.

### 6.2. Java DTOs

~~~java
public record BookView(
        String id,
        String title,
        Integer publishedYear) {
}

public record AuthorView(
        String id,
        String name,
        String biography) {
}
~~~

DTOs hold only the data needed to populate the GraphQL object types. DTOs can differ from persistence entities so the schema is not coupled directly to database structure.

### 6.3. Search Service

~~~java
@Service
class CatalogSearchService {

    List<Object> search(String keyword) {
        // Illustrative example: results can come from multiple data sources.
        return List.of(
                new BookView(
                        "book-42",
                        "Spring GraphQL",
                        2026
                ),
                new AuthorView(
                        "author-12",
                        "An Nguyen",
                        "Author writing about Java and GraphQL"
                )
        );
    }
}
~~~

In a real application, the service searches by keyword, enforces access permissions, and returns the matching DTOs. This fixed example focuses on demonstrating a list containing multiple kinds of source objects.

### 6.4. Controller

~~~java
@Controller
class CatalogController {

    private final CatalogSearchService searchService;

    CatalogController(CatalogSearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    List<Object> searchCatalog(@Argument String keyword) {
        return searchService.search(keyword);
    }
}
~~~

The controller does not need to manually construct `GraphQLObjectType` instances or build JSON responses. It returns Java data; the GraphQL runtime and `TypeResolver` determine the GraphQL type of each element.

### 6.5. Runtime Wiring

~~~java
@Configuration
class GraphQlUnionConfiguration {

    @Bean
    RuntimeWiringConfigurer unionTypeResolver() {
        ClassNameTypeResolver typeResolver =
                new ClassNameTypeResolver();

        typeResolver.addMapping(BookView.class, "Book");
        typeResolver.addMapping(AuthorView.class, "Author");

        return builder -> builder.type(
                "SearchResult",
                type -> type.typeResolver(typeResolver)
        );
    }
}
~~~

Once the configuration is loaded, the GraphQL runtime can resolve:

| Java Source Object | GraphQL Object Type |
| --- | --- |
| `BookView` | `Book` |
| `AuthorView` | `Author` |

The union resolver configuration applies to the abstract type `SearchResult`. If the schema has additional unions, each union needs mapping rules matching its own members.

### 6.6. Client-Side Operation

~~~graphql
query SearchCatalog($keyword: String!) {
    searchCatalog(keyword: $keyword) {
        __typename
        ... on Book {
            id
            title
            publishedYear
        }
        ... on Author {
            id
            name
            biography
        }
    }
}
~~~

Variables:

~~~json
{
    "keyword": "Spring"
}
~~~

The response can contain elements belonging to two different object types:

~~~json
{
    "data": {
        "searchCatalog": [
            {
                "__typename": "Book",
                "id": "book-42",
                "title": "Spring GraphQL",
                "publishedYear": 2026
            },
            {
                "__typename": "Author",
                "id": "author-12",
                "name": "An Nguyen",
                "biography": "Author writing about Java and GraphQL"
            }
        ]
    }
}
~~~

The client receives only the fields of the inline fragment matching the actual object type. For instance, the `Book` element does not have a `biography` field in the response.

## 7. Mapping Fields on Union Members

A union has no fields of its own, yet its member object types still have their own fields and resolvers.

Example schema:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author!
}

type Author {
    id: ID!
    name: String!
}

union SearchResult = Book | Author

type Query {
    searchCatalog(keyword: String!): [SearchResult!]!
}
~~~

When the client requests:

~~~graphql
query {
    searchCatalog(keyword: "Spring") {
        ... on Book {
            title
            author {
                name
            }
        }
        ... on Author {
            name
        }
    }
}
~~~

GraphQL resolves the fields according to the concrete object type:

- `Book.title` can be read from a property on `BookView` or its corresponding resolver.
- `Book.author` can be handled by `@SchemaMapping(typeName = "Book", field = "author")`.
- `Author.name` is resolved on the `Author` object type.

Example nested mapping:

~~~java
@Controller
class BookController {

    private final AuthorService authorService;

    BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    AuthorView author(BookView book) {
        return authorService.findByBookId(book.id());
    }
}
~~~

The union `TypeResolver` only determines whether a source object is a `Book` or an `Author`. Once determined, GraphQL proceeds to resolve the selected fields on that object type via property access or registered DataFetchers.

Do not write a `@SchemaMapping` method for the `SearchResult` union itself to handle shared fields, because a union defines no fields. If multiple members share a group of fields and clients need to query those shared fields directly, consider using an interface.

## 8. When to Use a Union vs. an Interface?

Unions and interfaces both allow a field to return multiple kinds of objects, but their contracts differ.

| Criterion | Union | Interface |
| --- | --- | --- |
| Purpose | Group object types that can appear in the same result | Define a shared set of fields implemented by object types |
| Shared field declaration | None | Yes |
| Client field selection | Use inline fragments for each member | Can select interface fields directly and use fragments for specific fields |
| Members | Object types | Object types implementing the interface |
| Example | `SearchResult = Book | Author` | `Node { id: ID! }` |

Use a union when results are heterogeneous and lack a meaningful shared field contract:

~~~graphql
union SearchResult = Book | Author | Publisher
~~~

Use an interface when all object types share a set of fields with the same semantics:

~~~graphql
interface Node {
    id: ID!
}

type Book implements Node {
    id: ID!
    title: String!
}

type Author implements Node {
    id: ID!
    name: String!
}
~~~

Clients can select `id` directly on `Node` and use inline fragments for specific fields. Do not create an interface just because objects happen to have fields with the same name if their meaning or data rules differ.

## 9. Testing Union Mapping

An integration test should verify both the returned results and the `__typename` of each element. `GraphQlTester` can execute operations and inspect the response by JSON path.

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query SearchCatalog($keyword: String!) {
            searchCatalog(keyword: $keyword) {
                __typename
                ... on Book {
                    id
                    title
                }
                ... on Author {
                    id
                    name
                }
            }
        }
        """)
        .variable("keyword", "Spring")
        .execute();

response.path("searchCatalog[0].__typename")
        .entity(String.class)
        .isEqualTo("Book");

response.path("searchCatalog[1].__typename")
        .entity(String.class)
        .isEqualTo("Author");
~~~

This test verifies that TypeResolver maps both source objects to their corresponding GraphQL object types.

### 9.1. Testing Fields per Fragment

In addition to `__typename`, verify that each object type's fields resolve properly:

~~~java
graphQlTester.document("""
        query {
            searchCatalog(keyword: "Spring") {
                ... on Book {
                    title
                }
                ... on Author {
                    name
                }
            }
        }
        """)
        .execute()
        .path("searchCatalog[0].title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

You can split these into separate tests to make it easier to pinpoint the cause when a member mapping is wrong.

### 9.2. Testing Unsupported Source Objects

If the service returns a class absent from the mapping, TypeResolver needs to detect that situation. Tests should verify that the operation reports an error rather than silently classifying the object as another type.

Scenarios to verify:

- Each Java class maps to the right GraphQL object type.
- Source objects of an unsupported class.
- Fields of each member resolve properly.
- Whether a member returning null complies with the union field's nullability.
- Non-matching inline fragments do not expose fields of another type.
- Nested field resolvers on members execute after TypeResolver finishes.

## 10. Common Mistakes When Mapping Unions

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Abstract type ... must resolve to an Object type` | TypeResolver could not identify the source object | Add a mapping for the Java class |
| `Unknown type SearchResult` | SDL does not declare the union or name is misspelled | Check the union name in SDL and runtime wiring |
| Java object is not recognized | Java class name differs from GraphQL object type | Use `ClassNameTypeResolver.addMapping` or a custom resolver |
| Resolver returns a class not in the union | Service returned a type outside declared members | Normalize results or intentionally update the schema |
| Client cannot query a field on the union | Union does not define shared fields | Use inline fragments or switch to an interface when appropriate |
| `__typename` returns unexpected name | Mapping points to the wrong object type | Check class-to-type mappings |
| Member's nested field is null or errors | Missing suitable DataFetcher/property for that field | Check `@SchemaMapping`, properties, and service |
| Added a new member but queries fail to handle it | Client lacks an inline fragment for the new type | Update clients and check fallback behavior based on `__typename` |

An important mistake is confusing union mapping with field mapping. TypeResolver only answers the question "which GraphQL type is this source object?". It does not itself load `author`, `reviews`, or other nested data.

## 11. Workflow for Implementing Union Mapping

When building a field that returns multiple object types, you can follow this sequence:

1. **Identify result kinds.** List the object types that can genuinely appear in the result.
2. **Choose union or interface.** Use a union when there are no shared fields; use an interface when there is a shared contract.
3. **Declare SDL.** Create the union from existing object types and declare the field returning the union.
4. **Design DTO/domain models.** Use separate classes or records for each result type.
5. **Write the controller.** Use `@QueryMapping` or `@SchemaMapping` to return appropriate source objects.
6. **Configure TypeResolver.** Map each Java class to the right GraphQL object type.
7. **Write sample operations.** Use `__typename` and inline fragments to select fields.
8. **Resolve nested fields.** Add `@SchemaMapping` or property access for each member's fields.
9. **Test.** Verify every mapping, fragment, unsupported case, and nullability error.
10. **Evolve the schema.** When adding a new member, check resolvers, clients, and existing operations using the union.

## 12. Summary

Unions allow a GraphQL field to return multiple distinct object types without forcing them into a shared field structure. Clients use `__typename` and inline fragments to select data according to the actual object type. In Spring for GraphQL, controllers can return a list of source objects of different classes; `TypeResolver` determines which GraphQL object type each object corresponds to.

`RuntimeWiringConfigurer` is where resolvers for unions are registered. `ClassNameTypeResolver` fits class-name-based mapping and supports explicit mappings for DTOs; a custom resolver fits when specific classification rules are needed. Once the union member is determined, member fields continue to be resolved via property access or `@SchemaMapping`. Testing `__typename`, inline fragments, and unsupported source object cases ensures union mapping works consistently from service to response.
