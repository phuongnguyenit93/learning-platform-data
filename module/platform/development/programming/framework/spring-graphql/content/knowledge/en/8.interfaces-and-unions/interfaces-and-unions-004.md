# TypeResolver in Spring for GraphQL

GraphQL interfaces and unions allow a field to return multiple concrete object types. When the server executes a query, it needs to know which GraphQL object type the Java object in hand corresponds to. `TypeResolver` handles determining that concrete type at runtime.

In Spring for GraphQL, you can register a `TypeResolver` via `RuntimeWiringConfigurer`. The resolver receives the source object from the data fetcher's result and returns the appropriate `GraphQLObjectType` in the schema. This mapping helps GraphQL select the right inline fragments, serialize the right fields, and provide the accurate `__typename` value.

## 1. Why Is TypeResolver Needed?

For a field with a concrete object type, GraphQL already knows the return structure. For example, `book: Book` always returns the `Book` object type. But if a field has an interface or union type, the result can be one of multiple object types.

For example, a search feature might return books or authors:

```graphql
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

union SearchHit = Book | Author

type Query {
    searchResults(keyword: String!): [SearchResult!]!
    searchHits(keyword: String!): [SearchHit!]!
}
```

`SearchResult` is an interface because both `Book` and `Author` share the `id` field. `SearchHit` is a union because it represents a result that can be a `Book` or an `Author`, without defining shared fields. Both interfaces and unions must be resolved to a concrete object type when GraphQL finalizes the result.

If a data fetcher returns a Java `Book` object, GraphQL must know that the object is the GraphQL type `Book`; if it returns an `Author`, it must select the GraphQL type `Author`. `TypeResolver` performs this determination step.

## 2. What Does TypeResolver Receive and Return?

In GraphQL Java, `TypeResolver` is a function that takes a `TypeResolutionEnvironment` and returns a `GraphQLObjectType`:

```java
import graphql.schema.TypeResolver;

TypeResolver resolver = environment -> {
    Object source = environment.getObject();

    if (source instanceof Book) {
        return environment.getSchema().getObjectType("Book");
    }

    if (source instanceof Author) {
        return environment.getSchema().getObjectType("Author");
    }

    throw new IllegalStateException("Unsupported runtime type");
};
```

Key parts:

- `environment.getObject()` returns the source object provided by the data fetcher for the interface or union field.
- `environment.getSchema()` provides access to the executing GraphQL schema.
- `getObjectType("Book")` retrieves the GraphQL object type named `Book` in the schema.
- The returned value must be a valid object type for the interface or union being resolved.

For an interface, the chosen object type must implement that interface. For a union, the chosen object type must be one of the members declared in the union. You must not return an arbitrary type or a type outside the allowed set of types.

## 3. Preparing Source Java Types

Example using Java records and a sealed interface to model search results:

```java
public sealed interface SearchItem permits Book, Author {
    String id();
}

public record Book(String id, String title) implements SearchItem {
}

public record Author(String id, String name) implements SearchItem {
}
```

`Book` and `Author` are two concrete Java types. Both implement `SearchItem`, so a service can return a shared list:

```java
import java.util.List;

public interface SearchService {
    List<SearchItem> search(String keyword);
}
```

In this example, `SearchItem` is a Java domain abstraction. It does not automatically become a GraphQL interface; the relationship between Java objects and GraphQL object types is determined by the `TypeResolver` registered in runtime wiring.

If the project uses a Java version that does not yet support sealed interfaces or records, you can replace them with regular interfaces and classes. What matters is that the resolver can identify each concrete object type, such as via `instanceof` or a reliable discriminator property.

## 4. Registering TypeResolver with RuntimeWiringConfigurer

Spring for GraphQL allows providing a `RuntimeWiringConfigurer` as a Spring bean. Spring Boot uses this configurer when building GraphQL runtime wiring.

Example registering the same `TypeResolver` for both the `SearchResult` interface and the `SearchHit` union:

```java
import graphql.schema.TypeResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlRuntimeConfig {

    @Bean
    RuntimeWiringConfigurer searchTypeResolverConfigurer() {
        TypeResolver searchTypeResolver = environment -> {
            Object source = environment.getObject();

            if (source instanceof Book) {
                return environment.getSchema().getObjectType("Book");
            }

            if (source instanceof Author) {
                return environment.getSchema().getObjectType("Author");
            }

            throw new IllegalStateException("Unsupported SearchItem runtime type");
        };

        return builder -> builder
                .type("SearchResult", type -> type.typeResolver(searchTypeResolver))
                .type("SearchHit", type -> type.typeResolver(searchTypeResolver));
    }
}
```

`type("SearchResult", ...)` configures wiring for the interface named `SearchResult`. The next line registers the resolver for the `SearchHit` union. Because both share the same object members `Book` and `Author`, they can share the classification logic.

If an interface and a union have different member sets, register an appropriate resolver for each type. A shared resolver is only safe when the types it returns are valid across every interface/union to which that resolver is attached.

## 5. Resolvers Returning an Interface or Union

A controller can return a list of concrete Java objects through a common type:

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
    public List<SearchItem> searchResults(@Argument("keyword") String keyword) {
        return searchService.search(keyword);
    }

    @QueryMapping
    public List<SearchItem> searchHits(@Argument("keyword") String keyword) {
        return searchService.search(keyword);
    }
}
```

`@QueryMapping` maps the method to a field on the root `Query`. The method returns the actual Java objects; when GraphQL needs to finalize each element whose type is an interface or union, `TypeResolver` determines the corresponding object type.

In this example, both methods use the same service to make the mapping clear. A real application can use two separate services or two separate methods if the search results of the interface and union differ.

## 6. Clients Querying with Inline Fragments

With an interface, the client can select shared fields declared on the interface, then use inline fragments to retrieve fields specific to each object type:

```graphql
query {
    searchResults(keyword: "spring") {
        __typename
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

With a union, the client can only directly select allowed meta-fields like `__typename`; concrete fields must reside inside inline fragments:

```graphql
query {
    searchHits(keyword: "spring") {
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

An illustrative response:

```json
{
  "data": {
    "searchResults": [
      {
        "__typename": "Book",
        "id": "book-1",
        "title": "Spring GraphQL"
      },
      {
        "__typename": "Author",
        "id": "author-1",
        "name": "Nguyen An"
      }
    ],
    "searchHits": [
      {
        "__typename": "Book",
        "id": "book-1",
        "title": "Spring GraphQL"
      },
      {
        "__typename": "Author",
        "id": "author-1",
        "name": "Nguyen An"
      }
    ]
  }
}
```

`__typename` is a meta-field provided by GraphQL and does not need to be declared in SDL. Its value indicates the concrete object type selected by `TypeResolver`. Clients commonly use this value to branch when rendering data or handling polymorphic results.

## 7. Distinguishing TypeResolver from Data Fetcher and SchemaMapping

The three components have distinct responsibilities:

| Component | Responsibility |
| --- | --- |
| `@QueryMapping` / data fetcher | Fetches data for a field, for example querying a list of search results. |
| `@SchemaMapping` | Fetches the value for a specific field on an object, for example `Book.author`. |
| `TypeResolver` | Determines the concrete GraphQL object type for a value being returned through an interface or union. |

For example, `searchResults` returns a list of objects. The data fetcher finds and returns the data. `TypeResolver` decides whether each element is a `Book` or an `Author`. Afterward, the fields in the selection set are resolved using the object's values and any corresponding data fetchers.

`TypeResolver` is not used to load data from a database, does not replace `@QueryMapping`, and is not an authorization mechanism. Once an object has been classified as `Book`, access permissions for the `Book.title` field still need to be checked using the application's appropriate security mechanism.

## 8. Handling Unresolvable Types

Some common issues when using `TypeResolver`:

- The data fetcher returns a Java class that the resolver does not recognize.
- The resolver returns a GraphQL type name that does not exist in the schema.
- The resolver returns an object type that does not implement the interface in use.
- The resolver returns an object type that is not in the union member list.
- One Java type is used in multiple places, but each place needs a different GraphQL type mapping.

Handle unsupported cases explicitly instead of returning null or arbitrarily picking a default type. For example:

```java
TypeResolver searchTypeResolver = environment -> {
    Object source = environment.getObject();

    if (source instanceof Book) {
        return environment.getSchema().getObjectType("Book");
    }
    if (source instanceof Author) {
        return environment.getSchema().getObjectType("Author");
    }

    throw new IllegalStateException(
            "No GraphQL object type configured for search result");
};
```

Error messages intended for clients should be handled through the application's GraphQL error mechanism so internal details are not exposed. Server logs can record the actual Java type and necessary request context to assist investigation.

If a Java class can correspond to multiple GraphQL object types depending on context, checking `instanceof` alone may not be enough. Use distinct subtypes or a discriminator in the domain model to decide the type unambiguously. Never infer the type from client-controlled data if doing so could cause the server to misclassify an object.

## 9. Testing TypeResolver with GraphQlTester

Tests should verify both specific field values and `__typename`. Example using `GraphQlTester` configured in the test context:

```java
@Test
void interfaceResultResolvesConcreteTypes() {
    graphQlTester.document("""
            query {
                searchResults(keyword: "spring") {
                    __typename
                    id
                    ... on Book { title }
                    ... on Author { name }
                }
            }
            """)
        .execute()
        .path("searchResults[0].__typename")
        .entity(String.class)
        .isEqualTo("Book");
}
```

You can write a similar test for the second element to confirm `Author`, and verify that `title` or `name` fields are returned accurately according to the fragments. For unions, check `__typename` and the fields that exist only inside each inline fragment.

Additional tests should cover:

1. Each Java subtype maps to the correct GraphQL object type.
2. Every returned object type is a valid member of the interface/union.
3. `__typename` matches each element in a mixed list.
4. Inline fragments return only fields of the corresponding object type.
5. An unsupported Java type produces a clear GraphQL error without leaking sensitive information.
6. An empty list still returns the expected result according to the declared nullability.

## 10. Common Mistakes and Fixes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Cannot resolve abstract type | No matching TypeResolver registered or runtime wiring not applied | Check `RuntimeWiringConfigurer` and interface/union names in SDL. |
| Always receiving the wrong `__typename` | Object classification condition is wrong or overly broad | Check actual subtypes and map each concrete class. |
| Inline fragment returns no fields | Resolver chose the wrong object type or fragment does not match actual type | Check the GraphQL type name and TypeResolver output. |
| TypeResolver returns an invalid object type | Type does not implement the interface or is not part of the union | Return only object types within the allowed set of types. |
| Adding a new subtype causes query errors | TypeResolver has not been updated to recognize the subtype | Add the mapping and tests for the new subtype. |
| Child fields still fail after type resolution | TypeResolver only identifies the object type, it does not supply field data | Check the source object and the field's data fetcher/`@SchemaMapping`. |

## 11. Checklist When Implementing TypeResolver

1. Declare the interface or union and the concrete object types in SDL.
2. Ensure object types implement all fields of the interface or are listed in the union.
3. Choose a reliable way to identify each concrete Java object.
4. Register the TypeResolver with `RuntimeWiringConfigurer` for the exact interface/union name.
5. Return only a valid GraphQL object type for the abstract type being resolved.
6. Handle unsupported Java types explicitly.
7. Verify `__typename` and inline fragments using `GraphQlTester`.
8. When adding a subtype, update the schema, mapping, and tests together.

`TypeResolver` bridges runtime Java objects and concrete GraphQL types within an interface or union. When mappings are registered accurately and fully reflect the domain subtypes, clients can query polymorphic data consistently with inline fragments while the server preserves a clear schema contract.
