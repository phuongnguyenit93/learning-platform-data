# Union Types in GraphQL

A **union type** is an abstract type in GraphQL that allows a field to return one of several different object types. Unions are useful when a search operation or a field can return multiple kinds of results that do not share a common set of fields.

For example, a system-wide search might return either a `Book` or an `Author`. The client does not need to call two separate APIs; a single GraphQL field can return a list of `SearchResult`, where each element is an object of one of those two types.

In Spring for GraphQL, the schema declares the union using SDL. Resolvers return the corresponding Java objects, while GraphQL Java needs to determine the concrete object type of each value at runtime through the type resolution mechanism.

## 1. Declaring a Union Type in SDL

A union is declared using the `union` keyword, followed by the union name and a list of member object types separated by `|`:

```graphql
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
    search(keyword: String!): [SearchResult!]!
}
```

In this example:

- `SearchResult` is the union type.
- `Book` and `Author` are the two object types that can appear in the result.
- `search` returns a non-null list; each element in the list must also be a valid non-null object belonging to `SearchResult`.
- Each actual element can be either a `Book` or an `Author`.

A union can only contain **object types**. You cannot add scalars, enums, input objects, interfaces, or another union as members. Member object types can have very different structures; a union does not require them to declare the same fields.

## 2. When Should You Use a Union?

A union is appropriate when a field can return multiple different object types and those types do not share a meaningful set of common fields to model with an interface.

For example, a search page might return:

```graphql
type Product {
    id: ID!
    name: String!
    price: Float!
}

type Article {
    id: ID!
    title: String!
    publishedAt: String
}

type Category {
    id: ID!
    label: String!
}

union SearchHit = Product | Article | Category

type Query {
    searchAll(keyword: String!): [SearchHit!]!
}
```

A result element might be a product, an article, or a category. These types may all have `id`, but each has its own domain fields. A union only states that the field returns one of those types; it does not create a shared `id` field.

Cases that often fit unions well:

- Aggregated search results from multiple data domains.
- A field returning different forms of content, such as `TextMessage`, `ImageMessage`, or `FileMessage`.
- An operation that can return different result objects, such as `PaymentSuccess` or `PaymentChallenge`.
- A feed containing multiple item types with distinct structures.

If the types share a clear set of common fields and represent a shared concept, an interface is usually a better choice.

## 3. Querying Unions with Inline Fragments

Clients cannot directly access member-specific fields of a union at the union level. To fetch fields of a concrete type, you must use an **inline fragment** with the `... on TypeName` syntax:

```graphql
query Search($keyword: String!) {
    search(keyword: $keyword) {
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
```

GraphQL only executes the selections inside fragments matching the runtime type of the element:

- If the element is a `Book`, the client receives `id` and `title`.
- If the element is an `Author`, the client receives `id` and `name`.
- `__typename` indicates the concrete object type name, such as `Book` or `Author`.

An illustrative response:

```json
{
  "data": {
    "search": [
      {
        "__typename": "Book",
        "id": "book-01",
        "title": "GraphQL in Practice"
      },
      {
        "__typename": "Author",
        "id": "author-01",
        "name": "An Nguyen"
      }
    ]
  }
}
```

`__typename` is a meta-field provided by GraphQL on objects, interfaces, and unions. It is especially helpful when clients need to distinguish result variants to render the appropriate component or update a cache.

### Named Fragments

If a fragment is used in multiple places, you can give the fragment a name:

```graphql
query Search($keyword: String!) {
    search(keyword: $keyword) {
        __typename
        ...BookFields
        ...AuthorFields
    }
}

fragment BookFields on Book {
    id
    title
}

fragment AuthorFields on Author {
    id
    name
}
```

Named fragments help reuse selection sets and make large queries easier to read. The type after the `on` keyword must be a valid member object type of the union or a type with a valid relationship under GraphQL fragment rules.

## 4. How Is a Union Different from an Interface?

Unions and interfaces are both abstract types, but they model two different relationships:

| Criterion | Union | Interface |
|---|---|---|
| Purpose | Group multiple object types that can substitute for each other on a field | Describe a shared field contract implemented by multiple object types |
| Declaration | `union SearchResult` with member object types | `interface Node { id: ID! }` |
| Shared fields | Declares no shared business fields | Declares required interface fields |
| Querying shared fields | Must use fragments per object type | Can directly query fields declared by the interface |
| Object type relationship | Object type is a union member | Object type declares `implements InterfaceName` |

Interface example:

```graphql
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

type Query {
    node(id: ID!): Node
}
```

With `Node`, the client can query `id` directly because it is a field of the interface:

```graphql
query {
    node(id: "item-01") {
        id
        __typename
        ... on Book {
            title
        }
        ... on Author {
            name
        }
    }
}
```

If using the union `SearchResult = Book | Author`, the client cannot write `search { id }` just because both `Book` and `Author` happen to have an `id` field. A union does not expose shared fields. The client must place `id` inside each inline fragment:

```graphql
search(keyword: "GraphQL") {
    ... on Book {
        id
        title
    }
    ... on Author {
        id
        name
    }
}
```

Choose an interface when types share a contract; choose a union when you need to represent a choice among object types without forcing them to share a common structure.

## 5. Resolvers in Spring for GraphQL

A resolver for a field returning a union typically returns Java objects belonging to one of the member types. For example:

```java
public record Book(String id, String title) {}

public record Author(String id, String name) {}
```

The search service can return a list containing both kinds of objects:

```java
@Controller
class SearchController {

    private final SearchService searchService;

    SearchController(SearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    List<Object> search(@Argument String keyword) {
        return searchService.search(keyword);
    }
}
```

The return type `List<Object>` is simply a general representation in Java. What matters is that each element must actually be an object corresponding to a member declared in `SearchResult`. You can use a common Java parent type or a Java interface if the domain design calls for it, while the GraphQL union still has its own member set defined in SDL.

### Determining the Object Type at Runtime

GraphQL Java needs to know which GraphQL object type each Java object corresponds to. For unions and interfaces, this determination is performed using a `TypeResolver`.

You can register a resolver for `SearchResult` using `RuntimeWiringConfigurer`:

```java
@Configuration
class GraphQlTypeResolverConfiguration {

    @Bean
    RuntimeWiringConfigurer searchResultTypeResolver() {
        return wiringBuilder -> wiringBuilder.typeResolver(
            "SearchResult",
            environment -> {
                Object value = environment.getObject();

                if (value instanceof Book) {
                    return environment.getSchema().getObjectType("Book");
                }

                if (value instanceof Author) {
                    return environment.getSchema().getObjectType("Author");
                }

                throw new IllegalStateException(
                    "Unsupported SearchResult type: " + value.getClass().getName()
                );
            }
        );
    }
}
```

`environment.getObject()` is the actual Java object returned by the field resolver. `TypeResolver` checks the Java type and returns the corresponding `GraphQLObjectType` in the schema. The example above maps `Book` to the GraphQL type `Book` and `Author` to the GraphQL type `Author`.

If the application uses a consistent convention mapping class names to GraphQL type names, you can use the class-name-based type resolution mechanism provided by Spring for GraphQL. When class names do not match, multiple packages contain classes with the same name, or complex mapping is needed, registering an explicit `TypeResolver` gives clear control over the result.

Do not return `null` or an object type that does not belong to the union when the runtime type is unrecognized. Handle unsupported cases explicitly so errors are detected early during execution and testing.

## 6. How Do Field Resolvers and TypeResolver Differ?

These two mechanisms participate together in execution but answer different questions:

| Mechanism | Question to Answer | Example |
|---|---|---|
| Field resolver (`@QueryMapping`, `@SchemaMapping`) | What is the value of the field? | Search and return a list of result objects. |
| TypeResolver | Which GraphQL object type does this runtime object belong to? | The Java `Book` object corresponds to `Book` in the union. |

The processing flow for a union field can be described as follows:

```text
Query.search(keyword)
        |
        | Field resolver returns List<Object>
        v
  [Book, Author, Book, ...]
        |
        | TypeResolver for each element
        v
  [GraphQL Book, GraphQL Author, GraphQL Book, ...]
        |
        | Apply matching inline fragments
        v
  Result according to the client's selection set
```

`TypeResolver` does not load data on behalf of the field resolver. It only determines the concrete type so GraphQL knows which fragment applies and which fields can be selected on that object.

## 7. Nullability and Lists of Unions

Unions follow the same nullability rules as other GraphQL types. For example:

```graphql
type Query {
    search(keyword: String!): [SearchResult!]!
    optionalSearch(keyword: String!): [SearchResult!]
}
```

- `[SearchResult!]!`: the field always returns a list; an empty list is allowed; individual elements cannot be `null`.
- `[SearchResult!]`: the field can return `null`, but if a list is present, individual elements cannot be `null`.

If an element is `null` in a `[SearchResult!]` list, the entire list becomes `null`. If the field is `[SearchResult!]!`, the `null` value of the list propagates further up to the parent field according to Non-null rules. Furthermore, if `TypeResolver` cannot determine a valid type for an element, type resolution raises an execution error; inspect the response and logs to find the unsupported object.

Typically, a search field should return an empty list when there are no results if the API contract wants to guarantee a list is always returned. Avoid using `null` instead of an empty list unless clients need to distinguish between those two states.

## 8. Testing Union Types

Testing should verify both the returned data and the runtime type recognized by GraphQL:

1. When the service returns `Book`, the response has `__typename: "Book"` and the `Book` fragment is executed.
2. When the service returns `Author`, the response has `__typename: "Author"` and the `Author` fragment is executed.
3. When the list contains multiple object kinds, each element is classified independently and accurately.
4. When the service returns a Java type not belonging to the union, the application records an appropriate error and does not return a wrong object type.
5. When there are no results, the response follows the nullability declared for the list field.

Example test using `GraphQlTester`:

```java
@GraphQlTest(SearchController.class)
class SearchControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    SearchService searchService;

    @Test
    void resolvesDifferentUnionMembers() {
        given(searchService.search("GraphQL")).willReturn(List.of(
            new Book("book-01", "GraphQL in Practice"),
            new Author("author-01", "An Nguyen")
        ));

        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    search(keyword: "GraphQL") {
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
            .execute();

        response.path("search[0].__typename").entity(String.class).isEqualTo("Book");
        response.path("search[0].title").entity(String.class).isEqualTo("GraphQL in Practice");
        response.path("search[1].__typename").entity(String.class).isEqualTo("Author");
        response.path("search[1].name").entity(String.class).isEqualTo("An Nguyen");
    }
}
```

This example illustrates the test structure; imports, the `given` static import, and SDL must be provided in the test context. Depending on the Spring Boot version, the mock bean annotation may be `@MockitoBean` or `@MockBean`. If testing `TypeResolver` in isolation, you can build the schema/runtime wiring in the test and pass each Java type into resolution one by one.

## 9. Common Mistakes

**Querying a field directly on a union.** The statement `search { id }` is invalid merely because every current member happens to have `id`. A union does not expose shared fields; fields must be placed inside inline fragments for each object type.

**Forgetting `__typename` when the client needs to distinguish results.** If the UI needs to render each result type using a different component, request `__typename` to identify the runtime type.

**Missing TypeResolver or wrong runtime type mapping.** The field resolver may return the right data, yet GraphQL still does not know which union member the object belongs to. Check the `TypeResolver` configuration and GraphQL object type names.

**Returning a Java type not in the union.** Every runtime value must map to an object type listed in the union. If the domain adds a new result type, update both the SDL and type resolution.

**Using a union when a shared contract is actually needed.** If clients always need to query a field like `id` without repeating fragments, consider an interface.

**Confusing TypeResolver with a field resolver.** A field resolver loads or computes values; a TypeResolver only determines the concrete object type for an already resolved value.

**Ignoring list nullability.** Check all possibilities: a `null` list, a `null` element, and no results. These choices directly affect the response when an element fails to resolve.

## Conclusion

Union types allow a GraphQL field to return multiple distinct object types without requiring them to share fields. Clients use inline fragments to query each type's specific data and `__typename` to identify the runtime type. In Spring for GraphQL, field resolvers return Java objects, while `TypeResolver` maps those objects to the corresponding GraphQL object types. Choose a union when modeling multiple result forms, use an interface when a shared field contract is needed, and test every member of the union.
