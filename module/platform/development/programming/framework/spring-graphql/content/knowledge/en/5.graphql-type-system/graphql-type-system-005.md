# Interface type

In GraphQL, an `interface` describes a common set of fields that multiple object types can implement together. It is useful when an API returns different kinds of objects that share certain attributes—for example, books and movies both having an identifier, title, and release date.

Clients can query the shared fields through the interface without knowing the concrete object type ahead of time. When type-specific data is needed, clients use inline fragments or named fragments. The server resolves the actual object type of each result so GraphQL executes the selected fields accurately.

In Spring for GraphQL, the SDL schema declares the interface and its implementing object types; controllers or resolvers supply the data, while a runtime type resolver helps GraphQL determine the concrete type when needed.

## 1. What problem does an interface type solve?

Suppose a digital library application manages books and magazines. Both content types have different fields, yet both share an identifier and a title. Without an interface, clients would have to issue separate queries or handle two independent structures even though most of the display UI is similar.

We can model the shared data using an interface:

```graphql
interface Publication {
    id: ID!
    title: String!
}

type Book implements Publication {
    id: ID!
    title: String!
    author: String!
}

type Magazine implements Publication {
    id: ID!
    title: String!
    issueNumber: Int!
}
```

`Publication` publishes a contract consisting of `id` and `title`. `Book` and `Magazine` must implement those fields, while being able to add their own fields such as `author` or `issueNumber`.

An interface is an abstract output type. It is not an object that can be instantiated directly in a response. When a field has type `Publication`, the actual value must belong to a concrete object type that implements that interface.

## 2. Declaring an interface in SDL

Basic syntax:

```graphql
interface InterfaceName {
    fieldA: String!
    fieldB(argument: ID): Int
}
```

An interface can declare fields and arguments just like an object type. Object types implement an interface using the `implements` keyword:

```graphql
interface Node {
    id: ID!
}

type Customer implements Node {
    id: ID!
    name: String!
}

type Order implements Node {
    id: ID!
    status: String!
}
```

When an object type implements an interface, it must provide every field required by the interface with a compatible type. An object type can declare additional fields of its own. If an object implements multiple interfaces, you can list them separated by `&`:

```graphql
interface Timestamped {
    createdAt: String!
}

type Customer implements Node & Timestamped {
    id: ID!
    createdAt: String!
    name: String!
}
```

In this example, `Customer` must satisfy both the `Node` and `Timestamped` contracts.

## 3. Compatibility rules between interfaces and object types

When designing an interface, keep the contract consistent between the interface and its implementing types.

- An object type must include every field declared in the interface.
- Each corresponding field must have the same name, and any arguments declared by the interface must have the same names, types, and default values.
- The output type of the object field must be the same as or more specific (covariant) than the interface field's type. For instance, if the interface returns `String`, the object can return `String!`.
- An object type may add its own fields to describe type-specific data.
- An object type must not add required arguments that a client querying through the interface cannot supply; any additional arguments must be optional.

Valid example of a more specific output type:

```graphql
interface SearchResult {
    title: String
}

type Book implements SearchResult {
    title: String!
    isbn: String!
}
```

`String!` is more specific than `String`: every valid value of `String!` is also a valid value of `String`. The reverse is not true, because `String` can be null.

Invalid example:

```graphql
interface SearchResult {
    title: String!
}

type Book implements SearchResult {
    title: String
}
```

The `Book` object could return `null` for `title`, whereas the interface promises this field is non-null. The schema cannot uphold the contract published by the interface.

An interface should contain only fields that are genuinely meaningful across all implementing types. If you have to add dummy fields or return unnatural values just to satisfy an interface, revisit the abstraction boundary.

## 4. Using an interface as a return type

Interfaces commonly appear as return types for query fields or nested fields. Example:

```graphql
interface Media {
    id: ID!
    title: String!
}

type Movie implements Media {
    id: ID!
    title: String!
    durationMinutes: Int!
}

type Series implements Media {
    id: ID!
    title: String!
    seasonCount: Int!
}

type Query {
    media(id: ID!): Media
    searchMedia(keyword: String!): [Media!]!
}
```

`media` can return a `Movie` or a `Series`. `searchMedia` can return a list containing items of different concrete types. From the schema's perspective, clients know for certain that every item has `id` and `title`.

Because an interface is an output type, it can be used as a field return type, including as list elements. Do not use interfaces as arguments or fields of input objects. GraphQL has dedicated input types such as scalars, enums, and input objects to describe data sent by clients.

## 5. Querying interfaces and using inline fragments

Clients can select shared fields directly on the interface:

```graphql
query {
    searchMedia(keyword: "spring") {
        id
        title
    }
}
```

To fetch fields that exist only on a specific object type, use an inline fragment:

```graphql
query {
    searchMedia(keyword: "spring") {
        id
        title
        ... on Movie {
            durationMinutes
        }
        ... on Series {
            seasonCount
        }
    }
}
```

GraphQL executes only the fragment that matches the concrete type of each result. An item of type `Movie` will include `durationMinutes`; an item of type `Series` will include `seasonCount`.

You can also use named fragments to reuse selection sets:

```graphql
fragment MediaSummary on Media {
    id
    title
}

query SearchMedia($keyword: String!) {
    searchMedia(keyword: $keyword) {
        ...MediaSummary
        ... on Movie {
            durationMinutes
        }
        ... on Series {
            seasonCount
        }
    }
}
```

The `MediaSummary` fragment applies to the `Media` interface, so it only selects fields guaranteed by the interface. Specific fragments on `Movie` or `Series` can access fields unique to each object type.

## 6. Identifying the concrete type with `__typename`

With an interface, clients often need to know the actual object type to render the right UI or handle results properly. GraphQL provides the `__typename` meta-field:

```graphql
query {
    searchMedia(keyword: "spring") {
        __typename
        id
        title
    }
}
```

The response can contain elements of different types:

```json
{
  "data": {
    "searchMedia": [
      {
        "__typename": "Movie",
        "id": "m-101",
        "title": "Spring Journey"
      },
      {
        "__typename": "Series",
        "id": "s-205",
        "title": "The Framework"
      }
    ]
  }
}
```

`__typename` returns the actual GraphQL object type name, not the Java class name. It is useful when clients cache entities, branch UI components, or process polymorphic data.

## 7. Runtime type resolution in GraphQL Java

When a field has an interface type, the GraphQL runtime must determine the concrete object type of each value before executing the selected fields. This process is called type resolution.

For example, the `searchMedia` resolver returns a Java list containing `Movie` and `Series`. GraphQL needs to know that the first element corresponds to GraphQL type `Movie` and the second corresponds to `Series`.

There are two common approaches:

1. Provide a `TypeResolver` for the interface that inspects the actual Java object and returns the corresponding `GraphQLObjectType`.
2. Configure an `isTypeOf` mechanism on the object types to determine whether a value belongs to that type.

Without an appropriate identification mechanism, queries selecting fields through an interface can fail with an unresolved type error at execution time.

## 8. Configuring TypeResolver with Spring for GraphQL

In Spring for GraphQL, you can register a `RuntimeWiringConfigurer` to configure a type resolver for an interface. Suppose the schema uses `Media`, `Movie`, and `Series` from above.

Java types representing the data:

```java
public interface MediaItem {
    String id();
    String title();
}

public record Movie(
    String id,
    String title,
    int durationMinutes
) implements MediaItem {}

public record Series(
    String id,
    String title,
    int seasonCount
) implements MediaItem {}
```

Registering the type resolver:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlRuntimeConfiguration {

    @Bean
    RuntimeWiringConfigurer mediaTypeResolver() {
        return builder -> builder.type("Media", typeWiring ->
            typeWiring.typeResolver(environment -> {
                Object source = environment.getObject();

                if (source == null) {
                    throw new IllegalStateException("Media source must not be null");
                }
                if (source instanceof Movie) {
                    return environment.getSchema().getObjectType("Movie");
                }
                if (source instanceof Series) {
                    return environment.getSchema().getObjectType("Series");
                }

                throw new IllegalStateException(
                    "Unsupported Media implementation: " +
                    source.getClass().getName()
                );
            })
        );
    }
}
```

`RuntimeWiringConfigurer` lets you add runtime configuration when building the GraphQL schema. The resolver reads the source object via `environment.getObject()`, checks the Java type, and retrieves the corresponding object type from the schema.

In real projects, handle a null `source` intentionally if your data model can return null. For an interface field declared non-null, the parent field's resolver must also ensure a valid value is returned.

The controller can return concrete implementations:

```java
import java.util.List;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class MediaController {

    private final MediaService mediaService;

    public MediaController(MediaService mediaService) {
        this.mediaService = mediaService;
    }

    @QueryMapping
    public List<MediaItem> searchMedia(@Argument String keyword) {
        return mediaService.search(keyword);
    }
}
```

Shared fields like `id` and `title` can be read from the object's properties or accessors. If custom data-fetching logic is needed, fields can be mapped with `@SchemaMapping`. The type resolver remains responsible for determining the actual object type for the interface.

## 9. How do Interfaces and Unions differ?

Both interfaces and unions allow a field to return multiple concrete object types. The difference is that an interface publishes a shared field contract, whereas a union only lists the possible member types.

| Criterion | Interface | Union |
| --- | --- | --- |
| Declares shared fields | Yes | No |
| Object types participate via | `implements` | Listed with `=` and `\|` |
| Querying fields directly | Can select interface fields | Must use fragments to select object type fields |
| Best suited when | Types share a common data contract | Types are distinct but can be returned by one field |

Union example:

```graphql
union SearchHit = Book | Author

type Query {
    search(keyword: String!): [SearchHit!]!
}
```

Clients must use fragments to select fields:

```graphql
query {
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
}
```

If `Book` and `Author` genuinely share a stable field contract such as `id` and `displayName`, an interface may express it better. If they have no meaningful shared fields, a union is usually a better fit.

## 10. Common mistakes when using interfaces

| Mistake | Cause | How to fix |
| --- | --- | --- |
| Object type missing an interface field | Contract not fully implemented | Add the field with a compatible type |
| Object field weaker than interface field | e.g., interface declares `String!` but object returns `String` | Adjust nullability or the interface contract |
| Using an interface in an input object | Interfaces are output types | Declare a separate input object |
| Querying type-specific fields directly on the interface | That field exists only on a concrete type | Use an inline fragment or named fragment |
| Runtime cannot identify the concrete type | Missing or misconfigured type resolver | Register a `TypeResolver` or appropriate `isTypeOf` logic |
| Interface has too many unshared fields | Wrong abstraction boundary | Split the interface or use a union |
| Assuming Java class name equals GraphQL type | Names in the two systems do not have to match | Map Java implementations explicitly to GraphQL object types |

When adding a new implementation, update the schema, runtime type resolution, and tests for queries with the corresponding fragments. If you forget the resolver update, the error may only surface when a client receives that new type.

## 11. When should you use an interface?

An interface is a good fit when these conditions occur together:

- Multiple object types share a stable, business-meaningful set of fields.
- Clients need to query a list or single result that can belong to multiple concrete types.
- The UI needs to display common fields first and then extend per specific type.
- Implementing types can adhere to the same rules for identity, nullability, and data reading.

Do not create an interface merely because two objects happen to share one field name. Consider the semantics of the contract: if `id` on two types has completely different scopes or usage, grouping them into one interface can mislead clients.

## 12. Checklist before publishing an interface

- Does the interface contain only fields truly shared across all implementations?
- Does each object type implement all required fields and compatible arguments?
- Does output field nullability uphold the interface's guarantees?
- Can fields returning the interface resolve to a concrete object type?
- Do sample queries use fragments for type-specific fields?
- Do clients need `__typename` for branching or caching?
- Are there tests covering every implementation and unsupported-type cases?

An `interface` lets a GraphQL schema express a shared contract across multiple object types. Clients query that contract consistently, while inline fragments let them fetch type-specific data. In Spring for GraphQL, the key is returning the right Java objects and configuring proper type resolution so GraphQL knows which concrete type to use. When the shared contract accurately reflects the business domain, interfaces make polymorphic APIs clear and extensible.
