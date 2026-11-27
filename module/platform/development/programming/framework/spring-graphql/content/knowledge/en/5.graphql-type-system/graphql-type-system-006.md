# Union type

## 1. What is a union type?

In GraphQL, a field usually returns a specific type such as `Book`, `String`, or `[Order!]!`. However, some business cases require a field to return multiple different kinds of objects. For instance, a system-wide search feature might find books, authors, or publishers. In such cases, forcing all results into a single object with many nullable fields often makes the schema hard to understand and forces clients to guess the result type.

GraphQL provides the **union type** to describe a value that can belong to one of several defined object types. A union is an abstract output type: it groups object types that may have no inheritance relationship or share no common set of fields.

Example declaration in Schema Definition Language (SDL):

```graphql
union SearchResult = Book | Author | Publisher
```

`SearchResult` can represent a `Book`, `Author`, or `Publisher` object. Each concrete value at execution time is still an actual object type. GraphQL must know that exact object type to validate the selection set and return the right fields.

Unions are commonly used as return types for fields in `Query`, `Mutation`, or `Subscription`. A union is not an object type and cannot be used as a root operation type.

## 2. Declaring a union in SDL

### Basic syntax

A union is declared with the `union` keyword, the union name, `=`, and a list of member object types separated by `|`:

```graphql
union SearchResult = Book | Author | Publisher

type Book {
    id: ID!
    title: String!
    isbn: String
}

type Author {
    id: ID!
    name: String!
    penName: String
}

type Publisher {
    id: ID!
    companyName: String!
}
```

Members of a union must be **object types**. You cannot declare a scalar, enum, input object, or another union as a member. Each member must also be a distinct object type; do not list the same type twice.

A union does not declare fields inside a type body like an object type does. The following syntax is invalid:

```graphql
union SearchResult {
    id: ID!
    title: String
}
```

If the result types share common fields and the API needs to publish a shared contract, consider an `interface`. A union is appropriate when the primary goal is to represent one of several different object types.

### Using a union on a field

A field can return a union directly or a list of unions:

```graphql
type Query {
    search(term: String!): [SearchResult!]!
    searchOne(id: ID!): SearchResult
}
```

In this example:

- `search` always returns a list; each element in the list must be an object belonging to `SearchResult`.
- `searchOne` can return an object belonging to the union or `null` if not found.
- `SearchResult` is an output type, so it can appear as a field's return type.

Unions are not input types. You cannot use a union as a field argument type or as an input variable type. If a client needs to send one of several input structures, design an appropriate input object or use separate fields/operations per business case.

## 3. Search example returning multiple object types

Suppose a library application allows keyword search. Results can be books, authors, or publishers. Complete schema for the example:

```graphql
union SearchResult = Book | Author | Publisher

type Query {
    search(term: String!): [SearchResult!]!
}

type Book {
    id: ID!
    title: String!
    isbn: String
}

type Author {
    id: ID!
    name: String!
    penName: String
}

type Publisher {
    id: ID!
    companyName: String!
}
```

When a client calls `search`, each element in the list can have a different shape. One result might be a `Book` with `title`, while another is an `Author` with `name`. The schema does not require these objects to share the same set of fields.

This is a key benefit of unions: the schema accurately models data diversity instead of creating an aggregate object like `SearchResult { book: Book, author: Author, publisher: Publisher }` where most fields are frequently `null`.

## 4. Querying a union with inline fragments

When querying a union, clients cannot directly select fields specific to individual object types because the union defines no shared fields. Clients must use **inline fragments** to specify which fields to select when the actual value belongs to a particular type.

Example:

```graphql
query Search($term: String!) {
    search(term: $term) {
        __typename
        ... on Book {
            id
            title
            isbn
        }
        ... on Author {
            id
            name
            penName
        }
        ... on Publisher {
            id
            companyName
        }
    }
}
```

Meaning of each part:

- `search(term: $term)` calls the field returning a list of union items.
- `... on Book` selects the fields in that branch only when the actual object is `Book`.
- `... on Author` selects the fields in that branch only when the actual object is `Author`.
- `... on Publisher` selects the fields in that branch only when the actual object is `Publisher`.
- `__typename` asks GraphQL to return the actual object type name for each item.

If a client writes `search { title }` directly, GraphQL rejects it because `title` is not a field declared on the `SearchResult` union. That field exists only on the `Book` object type.

### Illustrative response

Suppose the server finds one book, one author, and one publisher. The response might look like:

```json
{
  "data": {
    "search": [
      {
        "__typename": "Book",
        "id": "book-101",
        "title": "GraphQL in Practice",
        "isbn": "9780000000001"
      },
      {
        "__typename": "Author",
        "id": "author-12",
        "name": "Nguyen An",
        "penName": null
      },
      {
        "__typename": "Publisher",
        "id": "publisher-8",
        "companyName": "Example Publishing"
      }
    ]
  }
}
```

Each item contains only the fields from the fragment branch matching its actual type. `__typename` indicates the exact object type resolved by the server.

## 5. Role of `__typename`

`__typename` is a GraphQL meta-field that returns the name of the concrete object type being executed. For unions, this field is especially useful because clients need to distinguish member types after receiving the data.

For example, the client can handle results by type:

```javascript
switch (item.__typename) {
  case "Book":
    renderBook(item.title);
    break;
  case "Author":
    renderAuthor(item.name);
    break;
  case "Publisher":
    renderPublisher(item.companyName);
    break;
}
```

In JavaScript or TypeScript, `__typename` is commonly used as a discriminator to select the corresponding UI or processing branch. Code-generation tools for GraphQL operations can also rely on this field to represent results as a discriminated union.

Do not infer the object type from the presence of an optional field, such as `if (item.title)`. That field could be absent or have a `null` value depending on the data and schema. `__typename` is the explicit signal provided by GraphQL.

`__typename` can be selected directly in the union's selection set. Type-specific fields like `title`, `name`, or `companyName` must still reside inside an appropriate inline fragment or named fragment.

## 6. Using named fragments to reuse selection sets

When the same group of fields is used across multiple operations or locations, clients can declare **named fragments** on individual object types:

```graphql
fragment BookSummary on Book {
    id
    title
    isbn
}

fragment AuthorSummary on Author {
    id
    name
}

query Search($term: String!) {
    search(term: $term) {
        __typename
        ...BookSummary
        ...AuthorSummary
        ... on Publisher {
            id
            companyName
        }
    }
}
```

`BookSummary` applies only to `Book`, and `AuthorSummary` applies only to `Author`. GraphQL checks the fragment's type condition to ensure a fragment is only spread on an object type valid at that usage site.

Named fragments avoid repeating selection sets and keep large queries easier to read. However, fragments do not alter the schema structure or how the server determines runtime types; they are purely a client-side mechanism for reusing field selections.

## 7. Distinguishing Union types and Interface types

Unions and interfaces are both abstract output types, but they express two different meanings.

| Criterion | Union | Interface |
| --- | --- | --- |
| Purpose | Represents one of several object types | Defines a shared field contract for multiple object types |
| Declares shared fields | Has no fields of its own | Has fields that implementing objects must satisfy |
| Members | Object types only | Object types implementing the interface |
| Querying fields | Uses fragments to select each object type's fields | Can select fields declared on the interface directly and use fragments for type-specific fields |
| Relationship between types | Objects may be structurally unrelated | Objects share a field contract |

Interface example:

```graphql
interface Node {
    id: ID!
}

type Query {
    nodes: [Node!]!
}

type Book implements Node {
    id: ID!
    title: String!
}

type Author implements Node {
    id: ID!
    name: String!
}
```

With `Node`, clients can query `id` directly because it is a shared field published by the interface:

```graphql
query {
    nodes {
        id
        ... on Book {
            title
        }
        ... on Author {
            name
        }
    }
}
```

If result types only need to be grouped into a set of choices with no shared field contract, a union is usually a better fit. If the API needs to guarantee that every member has certain fields, an interface expresses that contract better.

## 8. Union types are not input types

Unions are output types only. GraphQL does not allow declaring an argument or input field with a union type:

```graphql
# Invalid: union is not an input type
type Mutation {
    saveResult(value: SearchResult!): Boolean!
}
```

If a client needs to send one of several data structures to the server, you can create an input object with a discriminator and corresponding input fields:

```graphql
enum SearchTargetKind {
    BOOK
    AUTHOR
}

input SearchTargetInput {
    kind: SearchTargetKind!
    bookId: ID
    authorId: ID
}

type Mutation {
    pinSearchTarget(input: SearchTargetInput!): Boolean!
}
```

At the business layer, the server must validate consistency: if `kind` is `BOOK`, `bookId` must be present and `authorId` must not be used; if `kind` is `AUTHOR`, the corresponding rule applies. Basic SDL cannot express all cross-field dependencies on input fields by itself, so application validation is required.

Do not confuse this input object workaround with a union. It is an application-defined input structure for accepting data from clients.

## 9. How does GraphQL determine the runtime type?

When a field resolver returns `SearchResult`, GraphQL knows the value belongs to an abstract type but needs to identify the concrete object type to continue executing fragments. This process is called **type resolution**.

For example, a search resolver returns a list of Java objects:

```java
public sealed interface SearchResult
        permits BookResult, AuthorResult, PublisherResult {
}

public record BookResult(String id, String title, String isbn)
        implements SearchResult {
}

public record AuthorResult(String id, String name, String penName)
        implements SearchResult {
}

public record PublisherResult(String id, String companyName)
        implements SearchResult {
}
```

The Java classes above represent data returned from the service. Java class names do not have to match object type names in the SDL, so the server needs an explicit mapping rule between them.

### Declaring a TypeResolver with Spring for GraphQL

Spring for GraphQL lets you configure GraphQL Java runtime wiring via a `RuntimeWiringConfigurer` bean. For the `SearchResult` union, you can register a `TypeResolver` to return the object type corresponding to each instance:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlTypeConfig {

    @Bean
    RuntimeWiringConfigurer searchResultTypeResolver() {
        return wiringBuilder -> wiringBuilder.type(
            "SearchResult",
            typeWiring -> typeWiring.typeResolver(environment -> {
                Object value = environment.getObject();

                if (value instanceof BookResult) {
                    return environment.getSchema().getObjectType("Book");
                }
                if (value instanceof AuthorResult) {
                    return environment.getSchema().getObjectType("Author");
                }
                if (value instanceof PublisherResult) {
                    return environment.getSchema().getObjectType("Publisher");
                }

                throw new IllegalStateException(
                    "Unsupported SearchResult type: " + value.getClass().getName()
                );
            })
        );
    }
}
```

`environment.getObject()` returns the Java value supplied by the data fetcher. The `TypeResolver` inspects the runtime type and returns the `GraphQLObjectType` with the corresponding name in the schema. If the resolver returns an unsupported class, the example throws a clear error instead of silently picking the wrong type.

Once type resolution is configured, the query resolver can return different implementations:

```java
import java.util.List;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class SearchController {

    private final SearchService searchService;

    public SearchController(SearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    public List<SearchResult> search(@Argument String term) {
        return searchService.search(term);
    }
}
```

`SearchService` is responsible for searching and returning instances of classes registered in the `TypeResolver`. Spring for GraphQL pairs the data fetcher with runtime wiring so the GraphQL engine knows how to process each element of the list.

### Things to check when type resolution fails

- The union name in `RuntimeWiringConfigurer` must match the union name in the SDL exactly.
- The returned object type name must exist and be a member of the union.
- The data fetcher must return the exact classes recognized by the `TypeResolver`.
- Every object kind that can appear in results must have a resolution branch.
- Do not return `null` or an object type that is not a member of the union for a value being resolved.

If GraphQL cannot determine the runtime type, the query can raise an abstract type resolution error even though the SDL parsed successfully. This is an execution-time error, distinct from syntax or schema validation errors.

## 10. Combining unions with pagination and filtering

Unions can be used inside paginated lists like any other output type. Example:

```graphql
type SearchPage {
    items: [SearchResult!]!
    nextCursor: String
    hasNextPage: Boolean!
}

type Query {
    search(term: String!, first: Int = 20, after: String): SearchPage!
}
```

Clients query results of various types within each page:

```graphql
query SearchPage($term: String!, $first: Int!, $after: String) {
    search(term: $term, first: $first, after: $after) {
        nextCursor
        hasNextPage
        items {
            __typename
            ... on Book {
                id
                title
            }
            ... on Author {
                id
                name
            }
            ... on Publisher {
                id
                companyName
            }
        }
    }
}
```

Unions do not provide pagination, sorting, or filtering mechanisms on their own. Those behaviors are defined by arguments and the wrapper output type around the union. The server must define a consistent ordering across result types, how cursors are constructed, and how changes to data are handled while a client pages through results.

## 11. Common mistakes when designing and using unions

| Mistake | Cause | How to fix |
| --- | --- | --- |
| Selecting fields directly on a union | Unions declare no shared fields | Use inline fragments or named fragments on object types |
| Declaring a scalar or interface as a member | Unions accept object types only | Create concrete object types or consider an interface if a shared field contract is needed |
| Using a union as an argument or input field | Unions are output types | Create an input object and business validation |
| Omitting `__typename` in the response | Hard for clients to distinguish object types in mixed data | Select `__typename` in the selection set |
| Not configuring type resolution | GraphQL does not know which object type a Java instance maps to | Register a `TypeResolver` or appropriate mapping mechanism |
| TypeResolver returns a type that is not a union member | Runtime type is invalid against the schema | Check the mapping and the SDL member list |
| Creating an overly broad union | Clients must handle many unrelated types and the schema is hard to evolve | Split unions by business purpose and query scope |
| Using a union when all types share required fields | Schema cannot express the shared contract | Consider an `interface` |

## 12. Testing union types

You should test the schema, runtime results, and how clients identify object types.

**SDL checks:** verify that every union member is an existing object type with no duplicates, and that the field returning the union is declared with appropriate nullability.

**Operation validation checks:** verify that type-specific fields can only be selected inside fragments with valid type conditions. An operation selecting `title` directly on `SearchResult` must be rejected.

**Type resolution checks:** prepare at least one instance for each member object type and verify that `__typename` in the response is `Book`, `Author`, and `Publisher` respectively. Also test the case where the service returns an unsupported implementation.

**Data checks:** verify that fields for the matching branch appear, fields from other branches are omitted, nullable values are handled properly, and an empty list still produces a schema-valid response.

With Spring GraphQL, you can use `GraphQlTester` to send operations and assert on responses without testing each resolver in isolation. Illustrative example:

```java
graphQlTester.document("""
    query Search($term: String!) {
        search(term: $term) {
            __typename
            ... on Book { title }
            ... on Author { name }
            ... on Publisher { companyName }
        }
    }
    """)
    .variable("term", "spring")
    .execute()
    .path("search[0].__typename")
    .entity(String.class)
    .isEqualTo("Book");
```

This example assumes the first element in the results is a `Book`. In a real test suite, test every member type thoroughly and avoid relying on result ordering unless the service guarantees that order.

## 13. Checklist before adding a union to the schema

- [ ] Does the union represent a set of object types that can appear on the same field?
- [ ] Are all members valid object types declared in the schema?
- [ ] Does the field returning the union have clear nullability and list structure?
- [ ] Do clients use inline fragments or named fragments to select type-specific fields?
- [ ] Do clients select `__typename` if runtime type differentiation is needed?
- [ ] Does the server have a `TypeResolver` or appropriate runtime type mapping?
- [ ] Is every Java class that can be returned mapped to the correct object type in the union?
- [ ] Is the union kept out of input types and root operation types?
- [ ] Has an interface been considered if objects need to share a common field contract?
- [ ] Are there tests for every member type and for invalid runtime type cases?

## Conclusion

A union type allows a GraphQL field to return one of several object types without forcing those objects to share common fields. SDL declares the member set using `union Name = TypeA | TypeB`; clients use inline fragments or named fragments to select fields per concrete type and use `__typename` to identify the runtime type.

In Spring for GraphQL, data fetchers can return Java instances of different classes. The server must configure type resolution so the GraphQL engine maps each instance to its corresponding object type in the SDL. Choose a union when describing a heterogeneous set of results; choose an interface when the API needs to publish a shared field contract. Good design ensures the schema reflects the business model clearly and lets clients handle mixed data safely.
