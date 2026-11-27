# GraphQL Type Resolution for Interfaces and Unions

In GraphQL, **type resolution** is the process of determining the concrete object type of a value when a field in the schema returns an abstract type (`interface` or `union`). The schema tells clients which types a field can return; at execution time, the server must determine which concrete type the current object belongs to so GraphQL can complete the response properly.

For example, a search feature might return books or articles. The schema declares the result as `SearchResult`, but when the server returns an object, GraphQL must know whether that object is a `Book` or an `Article`. Spring for GraphQL uses GraphQL Java's type resolver mechanism to perform this step.

## When Does GraphQL Need Type Resolution?

For a field with a concrete object type, such as `Product`, GraphQL already knows the data structure to resolve. However, a field with an interface or union type can receive multiple different object types. GraphQL must determine the actual type before applying the corresponding field selections.

For example:

```graphql
interface SearchHit {
  id: ID!
  title: String!
}

type Book implements SearchHit {
  id: ID!
  title: String!
  isbn: String!
}

type Article implements SearchHit {
  id: ID!
  title: String!
  url: String!
}

union SearchResult = Book | Article

type Query {
  featured: [SearchHit!]!
  search(term: String!): [SearchResult!]!
}
```

`SearchHit` is an interface defining shared fields. `Book` and `Article` implement that interface while having their own specific fields. `SearchResult` is a union indicating that a search result can be a `Book` or an `Article`.

When the resolver for `search` returns a list of Java objects, GraphQL needs to determine the concrete type of each element. Type resolution happens at execution time, after the operation has been parsed and validated against the schema.

## How Do Interfaces and Unions Differ During Resolution?

Both interfaces and unions are abstract types, but they describe contracts differently:

| Aspect | Interface | Union |
| --- | --- | --- |
| Purpose | Describes shared fields that multiple object types must provide. | Groups object types that may differ in structure into a single result type. |
| Members | Object types implement the interface using `implements`. | Member list is declared after the `=` sign. |
| Directly selectable fields | Fields declared on the interface can be selected directly. | No shared business fields; fragments must be used to select concrete object fields. |
| Type resolution | Determines the concrete object type implementing the interface. | Determines the concrete object type belonging to the union. |

With an interface, clients can select shared fields and then use inline fragments for specific fields:

```graphql
query Featured {
  featured {
    __typename
    id
    title
    ... on Book {
      isbn
    }
    ... on Article {
      url
    }
  }
}
```

With a union, clients use fragments to select fields of each member:

```graphql
query Search($term: String!) {
  search(term: $term) {
    __typename
    ... on Book {
      id
      title
      isbn
    }
    ... on Article {
      id
      title
      url
    }
  }
}
```

`__typename` is a GraphQL meta-field that returns the concrete object type name at runtime. It is especially useful when clients receive data from an interface or union and need to distinguish each case.

## Two Phases: Validation and Runtime Resolution

Type resolution does not replace schema validation. The two steps serve different roles:

1. **Validation:** GraphQL checks the operation against the schema. For example, `isbn` may only be selected inside a fragment targeting `Book`; `url` may only be selected inside a fragment targeting `Article`.
2. **Runtime type resolution:** When a resolver returns an object for a field typed as an interface or union, the server identifies that object as a valid member type. GraphQL uses the concrete type to resolve fields in the selection set.

For example, the following operation is invalid because `isbn` is not a field on the `SearchHit` interface and is not inside a `Book` fragment:

```graphql
query InvalidFeatured {
  featured {
    id
    isbn
  }
}
```

Validation catches this error before calling the resolver. Conversely, if the operation is valid but the type resolver fails to determine whether the returned object is a `Book` or an `Article`, the error only appears during execution.

## TypeResolver in GraphQL Java

GraphQL Java provides the `TypeResolver` interface to map a runtime object to a `GraphQLObjectType` in the schema. The resolver receives a `TypeResolutionEnvironment`; from it, you can read the source object via `getObject()` and obtain the object type declared in the schema via `getSchema()`.

A common strategy is checking the Java type of the object:

```java
import graphql.schema.TypeResolver;

TypeResolver searchTypeResolver = environment -> {
    Object source = environment.getObject();

    if (source instanceof Book) {
        return environment.getSchema().getObjectType("Book");
    }

    if (source instanceof Article) {
        return environment.getSchema().getObjectType("Article");
    }

    return null;
};
```

For a `Book` object, the resolver returns the `GraphQLObjectType` named `Book`. For an `Article` object, the resolver returns the `Article` type. If the object does not belong to any known type, the resolver cannot determine the concrete type; returning `null` causes GraphQL to report a type resolution error during execution.

The type resolver must return a valid object type that is a possible type of the abstract type being resolved. Do not return an arbitrary type just because that type name exists in the schema.

## Registering TypeResolver in Spring for GraphQL

Spring for GraphQL lets you register GraphQL Java configuration through a `RuntimeWiringConfigurer` bean. You can register type resolvers for interfaces and unions in the same configuration:

```java
import graphql.schema.TypeResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlRuntimeConfiguration {

    @Bean
    RuntimeWiringConfigurer abstractTypeResolvers() {
        TypeResolver resolver = environment -> {
            Object source = environment.getObject();

            if (source instanceof Book) {
                return environment.getSchema().getObjectType("Book");
            }
            if (source instanceof Article) {
                return environment.getSchema().getObjectType("Article");
            }
            return null;
        };

        return builder -> {
            builder.type("SearchHit", type -> type.typeResolver(resolver));
            builder.type("SearchResult", type -> type.typeResolver(resolver));
        };
    }
}
```

`SearchHit` and `SearchResult` are two abstract types in the SDL. Both share the same set of possible types in this example, so they can share the strategy for identifying `Book` and `Article`. If an interface and union have different member sets, register an appropriate resolver for each abstract type.

Spring Boot / Spring for GraphQL collects `RuntimeWiringConfigurer` beans when building `GraphQlSource`, then applies this configuration to GraphQL Java's runtime wiring. Thus, in a standard Spring Boot application, you do not need to manually build a separate `GraphQLSchema` just to register a resolver.

## Combining Resolvers with Controller Mappings

The controller provides data for the root field; the type resolver determines the concrete type of each object; then field resolvers continue handling the selected fields on that object.

Example of a simple Java model:

```java
public interface SearchHit {
    String getId();
    String getTitle();
}

public class Book implements SearchHit {
    private String id;
    private String title;
    private String isbn;

    // constructors and getters
}

public class Article implements SearchHit {
    private String id;
    private String title;
    private String url;

    // constructors and getters
}
```

The query controller can return objects of different types in the same list:

```java
@Controller
public class SearchController {

    private final SearchService searchService;

    public SearchController(SearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    public List<SearchHit> featured() {
        return searchService.featured();
    }

    @QueryMapping
    public List<Object> search(@Argument String term) {
        return searchService.search(term);
    }
}
```

`featured()` returns actual objects that are `Book` or `Article`, both implementing the Java interface `SearchHit`. `search()` can also return a mixed list of objects; the Java collection's declared type does not replace GraphQL's type resolver.

Once GraphQL has identified an object as `Book`, field mappings for `Book` can be applied. For example:

```java
@SchemaMapping(typeName = "Book", field = "publisher")
public Publisher publisher(Book book) {
    return publisherService.findByBookId(book.getId());
}
```

Here `@SchemaMapping` handles the `publisher` field of the `Book` object type. It does not decide whether the initial abstract object is `Book` or `Article`; that responsibility belongs to the type resolver.

## Using a Discriminator Instead of instanceof

Not every application has a separate Java class for each GraphQL object type. Some systems use unified DTOs, records, maps, or data from external services. In those cases, you can rely on a validated discriminator in the data:

```java
TypeResolver resolver = environment -> {
    SearchDocument document = (SearchDocument) environment.getObject();

    return switch (document.kind()) {
        case "BOOK" -> environment.getSchema().getObjectType("Book");
        case "ARTICLE" -> environment.getSchema().getObjectType("Article");
        default -> null;
    };
};
```

`kind` is an application-defined property used to classify objects. Ensure this value comes from trusted data and only maps to permitted object types in the schema. Never take an arbitrary type name directly from client input and use it to select a GraphQL object type.

For systems with many result types, you can extract the identification logic into a service or component for easier testing and to avoid duplication across multiple type resolvers.

## Handling Unidentified Types

Type resolution can fail in several cases:

- The resolver returns an object not belonging to any concrete type declared for the interface or union.
- The type resolver checks the wrong class or discriminator.
- The schema renames an object type, but the mapping logic has not been updated.
- An object type is returned that is not a possible type of the abstract type being processed.
- Data from an external system is missing or has an invalid discriminator.

When a type resolver fails to return a valid type, GraphQL raises an execution error. Null values propagate according to the nullability rules of the field containing the abstract type. For example, if the field is `[SearchResult!]!`, a non-nullable element failing to resolve can cause the list to become null; since the list is also non-nullable, null can propagate further up to the parent field.

Never silently coerce an unrecognized object into a default type. Doing so can send malformed structures to clients or mask integration bugs. Log sufficient technical context without logging sensitive data, and return an appropriate error through the application's error-handling mechanism.

## Testing Type Resolution

Tests should verify both interface/union branches and unrecognized data cases.

Example using `GraphQlTester` to test a union:

```java
@Test
void searchResolvesConcreteTypes() {
    graphQlTester.document("""
        query {
          search(term: "spring") {
            __typename
            ... on Book {
              id
              title
              isbn
            }
            ... on Article {
              id
              title
              url
            }
          }
        }
        """)
        .execute()
        .path("search[0].__typename")
        .entity(String.class)
        .isEqualTo("Book");
}
```

This test assumes the first test item from `search` is a `Book`. Add further tests for `Article`, the `SearchHit` interface, a list mixing multiple concrete types, and an unrecognized object. For error cases, verify both `errors` and how null propagates according to the SDL.

When testing runtime wiring configuration, start the application or `GraphQlSource` in the test to verify the `RuntimeWiringConfigurer` bean is actually applied. Testing the `instanceof` function in isolation is not enough to prove the resolver is registered in the running schema.

## Common Implementation Mistakes

| Symptom | Possible Cause | How to Check or Fix |
| --- | --- | --- |
| Reports inability to resolve concrete type | Missing TypeResolver or resolver does not recognize the object. | Register a resolver for the interface/union and check class/discriminator. |
| Fragment matches schema but field returns null | Wrong runtime type resolved or object does not supply field data. | Check `__typename`, the resolver, and the concrete type's field mappings. |
| TypeResolver returns an invalid object type | Type is not among possible types of the interface/union. | Only return members declared in the SDL. |
| Interface works but union fails | Resolver registered only for the interface, not yet for the union. | Register separate type resolvers for each abstract type. |
| Object-specific field is not returned | Client did not use an inline fragment or fragment does not apply to the concrete type. | Check the selection set and object type name in the fragment. |
| Renaming a class breaks resolution | Logic based on class name or discriminator no longer matches. | Synchronize mapping with the schema and add runtime tests. |

When debugging, start by adding `__typename` to the query. This value shows which concrete type GraphQL selected. Next, check the SDL, possible types, the actual object returned by the resolver, and the `RuntimeWiringConfigurer` configuration.

## Key Takeaways

GraphQL type resolution determines the concrete object type for a field returning an interface or union. Interfaces provide shared fields; unions simply list the object types that can appear. Clients use inline fragments to select specific fields and `__typename` to learn the actual type.

In Spring for GraphQL, register a `TypeResolver` via `RuntimeWiringConfigurer`. The resolver typically relies on the Java class or a trusted discriminator to return the corresponding `GraphQLObjectType`. Only after the concrete type is determined does GraphQL apply that object's field selections and mappings. Test all member types thoroughly and handle unrecognized types explicitly.
