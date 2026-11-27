# Object Implements Interface

In GraphQL, an **interface** defines a contract consisting of fields that multiple object types provide together. When an object type declares `implements`, that object commits to having all fields of the interface with compatible data types. As a result, a field can return an interface so clients work with multiple kinds of objects through the same set of shared fields, then use inline fragments to fetch type-specific data.

For example, a search page can return books or articles. Both have `id` and `title`, while a book has `isbn` and an article has `url`. We declare the `SearchResult` interface, then have `Book` and `Article` implement this interface.

```graphql
interface SearchResult {
    id: ID!
    title: String!
}

type Book implements SearchResult {
    id: ID!
    title: String!
    isbn: String!
    availableCopies: Int!
}

type Article implements SearchResult {
    id: ID!
    title: String!
    url: String!
}

type Query {
    search(keyword: String!): [SearchResult!]!
}
```

`Book` and `Article` must both provide `id` and `title` according to the contract of `SearchResult`. Each object can still declare additional type-specific fields. The `Query.search` field returns a list of values belonging to the interface, so a result can be either a `Book` or an `Article`.

## 1. Interface Is a GraphQL Contract

An interface in SDL is an abstract output type. It describes the fields that every implementing object type must provide. An interface is not a concrete object type and cannot be returned as a standalone instance; at execution time, every actual value must correspond to a concrete object type.

A simple example:

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
```

`Node` exposes the `id` field. Both `Book` and `Author` can be used wherever the schema requires `Node`, such as a query returning `Node`:

```graphql
type Query {
    node(id: ID!): Node
}
```

This allows clients to query `id` without needing to know whether the actual object is a book or an author. If type-specific fields like `title` or `name` are needed, the client uses a fragment conditioned on the object type.

A GraphQL interface is a contract at the API layer. Java classes can use a Java interface to share behavior or types, but a GraphQL interface and a Java interface are two distinct concepts. You can use a Java interface to model return values, but GraphQL does not automatically infer the entire schema from Java interfaces; the SDL must still declare the interface and the `implements` relationship.

## 2. The `implements` Syntax

An object type declares the interface it implements immediately after the type name:

```graphql
type Book implements SearchResult {
    id: ID!
    title: String!
    isbn: String!
}
```

An object can implement multiple interfaces. Use `&` to separate the interface names:

```graphql
interface Node {
    id: ID!
}

interface Named {
    name: String!
}

type Author implements Node & Named {
    id: ID!
    name: String!
    biography: String
}
```

In this example, `Author` must satisfy the contracts of both `Node` and `Named`. It can include an extra `biography` field because object types are allowed to provide fields not in the interface.

An interface can also implement another interface. When using interface inheritance, an object type needs to satisfy the contract of the direct interface and all inherited interfaces according to the rules of the GraphQL type system. This capability depends on the version of GraphQL Java used by the application; ensure that the runtime version supports the corresponding syntax and validation.

## 3. Compatibility Rules When Implementing an Interface

GraphQL checks whether an object type actually satisfies the interface contract when building the schema. Important rules include:

| Rule | Requirement |
| --- | --- |
| Required fields | The object must have all fields declared in the interface |
| Output type | The return type of the object field must be equal to or a valid subtype of the return type in the interface |
| Field arguments | Arguments declared by the interface must exist on the corresponding object field with compatible names and types |
| Additional arguments | The object may add its own arguments if those arguments are not required for existing clients |
| Type-specific fields | The object is allowed to add fields that do not appear in the interface |
| Multiple interfaces | The object must satisfy the contracts of all interfaces it declares to implement |

### Fields Must Exist and Have Compatible Types

If the interface declares:

```graphql
interface Resource {
    id: ID!
    label: String!
}
```

An implementing object must have both `id` and `label`:

```graphql
type Book implements Resource {
    id: ID!
    label: String!
    isbn: String
}
```

If `label` is omitted, or its type is changed to `Int`, the schema does not satisfy the contract. The object can provide a more specific return type when that type is a valid subtype, but it cannot make the output type less compatible.

### Nullability and Output Type Covariance

The return type of a field on an object can be more specific than the interface's type. A common example is when an interface declares a nullable type while the object guarantees returning a non-null value:

```graphql
interface SearchResult {
    title: String
}

type Book implements SearchResult {
    title: String!
    isbn: String!
}
```

`String!` is a more specific type than `String`: the object commits to returning a value, whereas the shared contract only requires a nullable string. The reverse is invalid: if the interface declares `title: String!`, the object cannot implement it as `title: String` because doing so would allow the object to return null where the client was promised a value would always exist.

The same rule applies to lists and nested output types. For instance, `[Book!]!` can be a more specific return type than `[SearchResult!]` if `Book` is an object type implementing `SearchResult` and the wrappers satisfy the subtype rules. When designing a schema, choose the interface's nullability based on the common guarantee that all implementing objects can uphold.

### Arguments Must Preserve the Contract

If an interface defines an argument, the object must keep that argument with a compatible name and type:

```graphql
interface Searchable {
    search(keyword: String!): [SearchResult!]!
}

type Catalog implements Searchable {
    search(keyword: String!): [SearchResult!]!
    searchByCategory(category: ID!): [Book!]!
}
```

The object can add its own arguments, such as `category`, on a separate field. If you want to add an argument to the interface-implementing field itself, the extra argument must not become required in a way that prevents a valid client calling through the interface from calling the object field.

The following example is invalid because `locale` is a new required argument that the interface does not require:

```graphql
interface Named {
    displayName: String!
}

type Author implements Named {
    displayName(locale: String!): String!
}
```

A client that only knows the `Named.displayName` contract will not know to supply `locale`, whereas the object's resolver requires that argument. If the additional argument has a default value or is nullable, it is not mandatory for the client and can comply with the implementation rules.

## 4. Interface Fields and Object-Specific Fields

When a client queries through an interface, the client can only select directly the fields declared in the interface. Object-type-specific fields must be selected using fragments.

With the `SearchResult` schema, the following query is valid:

```graphql
query SearchCatalog {
    search(keyword: "Spring") {
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

`id` and `title` are shared fields so they are selected directly. `isbn` exists only on `Book`, while `url` exists only on `Article`, so the inline fragments `... on Book` and `... on Article` are needed.

Named fragments can be used if the selection set is reused:

```graphql
fragment BookFields on Book {
    isbn
}

fragment ArticleFields on Article {
    url
}

query SearchCatalog {
    search(keyword: "GraphQL") {
        id
        title
        ...BookFields
        ...ArticleFields
    }
}
```

If `isbn` is selected directly on `SearchResult`, GraphQL validation will report that the field does not exist on the interface. Fragments allow clients to access type-specific fields while keeping the query valid across multiple object types.

## 5. `__typename` and the Actual Object Type

GraphQL provides the meta field `__typename` so clients know the concrete object type name at runtime. This field is especially useful when a query returns an interface or union:

```graphql
query SearchCatalog {
    search(keyword: "Spring") {
        __typename
        id
        title
    }
}
```

The response can contain multiple object types within the same list:

```json
{
  "data": {
    "search": [
      {
        "__typename": "Book",
        "id": "book-01",
        "title": "Spring in Action"
      },
      {
        "__typename": "Article",
        "id": "article-02",
        "title": "GraphQL API Design"
      }
    ]
  }
}
```

The client can use `__typename` to choose how to render or decode the data. The returned name is the object type name in the GraphQL schema, which does not necessarily match the Java class name.

## 6. Type Resolution: How Does GraphQL Determine the Concrete Object?

An interface is an abstract type, so when a resolver returns an object for a field whose type is an interface, GraphQL Java needs to know which GraphQL object type that object belongs to. This process is called **type resolution**.

Type resolution is distinct from data fetching:

- `DataFetcher` retrieves the data for a field, for example `Query.search` returning a list of results.
- `TypeResolver` determines the concrete GraphQL type for each object in the list, for example the Java object `Book` corresponds to the GraphQL type `Book`.
- Child fields are then resolved by appropriate resolvers or the default property fetcher.

If the runtime cannot determine the concrete object type, GraphQL cannot complete executing the field returning the interface. Therefore, a valid schema alone is not enough; the application must configure type resolution appropriate for the actual object types.

## 7. Integrating Object Implements Interface in Spring for GraphQL

SDL declares the interface and implementing object types. The controller can return a shared Java interface or an appropriate parent type for the query:

```java
public interface SearchResult {
    String id();
    String title();
}

public record Book(
        String id,
        String title,
        String isbn) implements SearchResult {
}

public record Article(
        String id,
        String title,
        String url) implements SearchResult {
}
```

The root resolver returns concrete objects:

```java
@Controller
public class SearchController {

    private final SearchService searchService;

    public SearchController(SearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    public List<SearchResult> search(@Argument String keyword) {
        return searchService.search(keyword);
    }
}
```

`SearchService` can return a list containing `Book` and `Article`. However, declaring the Java interface `SearchResult` does not automatically replace GraphQL's type resolver. Spring for GraphQL connects GraphQL Java with controllers, while GraphQL Java still needs to identify the concrete object type for each element.

### Configuring TypeResolver via RuntimeWiringConfigurer

You can configure a `TypeResolver` for a GraphQL interface using `RuntimeWiringConfigurer`:

```java
@Bean
RuntimeWiringConfigurer searchResultTypeResolver() {
    return builder -> builder.type("SearchResult", type ->
        type.typeResolver(environment -> {
            Object source = environment.getObject();

            if (source instanceof Book) {
                return environment.getSchema().getObjectType("Book");
            }

            if (source instanceof Article) {
                return environment.getSchema().getObjectType("Article");
            }

            throw new IllegalArgumentException(
                "Unsupported SearchResult type: " + source.getClass().getName());
        })
    );
}
```

The resolver reads the source object returned from the parent field and maps the Java class to the corresponding `GraphQLObjectType`. When adding a new result kind, such as `Video`, you need to update the schema, data class, and type resolution so the runtime recognizes the new type.

For projects following a naming convention where Java class names match GraphQL type names, you can consider Spring for GraphQL's `ClassNameTypeResolver`. When class names and GraphQL type names differ or the domain model is complex, an explicit `TypeResolver` is often easier to control. Whichever approach you choose, test the actual object types returned.

### Resolvers for Object-Specific Fields

Specific fields of `Book` can use `@SchemaMapping`:

```java
@Controller
public class BookController {

    private final InventoryService inventoryService;

    public BookController(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @SchemaMapping(typeName = "Book", field = "availableCopies")
    public int availableCopies(Book book) {
        return inventoryService.availableCopies(book.id());
    }
}
```

If `isbn` is a property readable directly from the `Book` record, GraphQL Java can use the default property fetcher and does not need a separate resolver. Use `@SchemaMapping` when you need to call a service, transform data, or apply business logic. The `url` field of `Article` can be handled similarly with `typeName = "Article"`.

## 8. Interfaces and DataLoader

An interface field can be implemented by multiple object types. If that field needs to query related data, the optimization approach remains the same as for regular fields: use `@BatchMapping` or DataLoader to batch data loads.

For example, `SearchResult` has an `owner` field returning an interface `Node`:

```graphql
interface Node {
    id: ID!
}

interface SearchResult {
    id: ID!
    title: String!
    owner: Node
}

type Book implements SearchResult {
    id: ID!
    title: String!
    owner: Author
    isbn: String!
}

type Article implements SearchResult {
    id: ID!
    title: String!
    owner: Author
    url: String!
}

type Author implements Node {
    id: ID!
    name: String!
}
```

Here `Author` is an object type implementing `Node`, so `Book.owner` and `Article.owner` can return the concrete type `Author`, compatible with the `Node` type in the interface. If a query returns many results and each result needs to load its own owner, the resolver can cause N+1 queries. Use DataLoader to collect owner IDs and query in batches. In Spring for GraphQL, `BatchLoaderRegistry` and `@BatchMapping` are built-in mechanisms for this goal.

## 9. Testing Object Implementations and Type Resolution

You should test at least three layers of behavior:

1. Schema validation: every object type implementing the interface has all required fields and compatible types.
2. Type resolution: each Java class is mapped to the correct GraphQL object type.
3. Operations: clients querying shared fields, `__typename`, and specific fields via inline fragments receive accurate data.

Example with `GraphQlTester`:

```java
graphQlTester.document("""
        query {
            search(keyword: "Spring") {
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
        """)
    .execute()
    .path("search[0].__typename")
    .entity(String.class)
    .isEqualTo("Book");
```

In addition to checking the first element, test cases containing all object kinds in the list, an empty list, and cases where the service returns a class not yet supported by the type resolver. These cases help catch mapping errors before the API is consumed by clients.

## 10. Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Schema reports object has not fully implemented interface | Missing field or wrong return type | Add missing fields and check types/nullability |
| Interface field has argument but object is missing it | Field signature does not meet contract | Keep all arguments with the interface's names and types |
| Object adds a required argument to implemented field | Client calling through interface does not know the new argument | Remove the required argument or design a separate field |
| Object makes an interface non-null field nullable | Object no longer guarantees the contract | Keep non-null or adjust the interface if business logic permits |
| Query cannot select specific field | Field does not belong to the interface | Use an inline fragment or named fragment |
| Abstract type cannot be resolved | No suitable TypeResolver or unmapped class | Configure a type resolver and handle all object kinds |
| `__typename` is unexpected | Wrong Java class to GraphQL type mapping | Check the object type name returned by the resolver |
| Adding an interface field breaks multiple objects | Implementing objects have not been updated yet | Update all implementations or narrow the contract |

When the schema fails to start, check validation errors for the `implements` relationship. When the schema starts successfully but queries return an abstract type error, check `TypeResolver`. If the type is resolved but child fields have wrong data, check `DataFetcher`, `@SchemaMapping`, and the source object.

## 11. Interface Design Principles

Only include in an interface fields that genuinely have shared meaning across all implementing objects. A field that only fits `Book` should not be added to the `SearchResult` interface if `Article` has no way to provide equivalent data. Keep interfaces small and stable so clients can rely on the shared contract without needing to understand every detail of each object.

Choose nullability according to the guarantee every implementation can satisfy. Avoid adding required arguments to implemented fields or weakening the output type compared to the interface. When adding a field to an interface used by many objects, check all implementations and evaluate the impact on clients.

In Spring for GraphQL, keep a clear boundary between three responsibilities: SDL describes the interface and object contracts; resolvers fetch data for fields; the type resolver determines the concrete GraphQL object when a field returns an interface. When these three parts are configured consistently, the API can return multiple object kinds through a single field while keeping the schema clear and type-safe.
