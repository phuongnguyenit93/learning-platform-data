# When to Use an Interface vs. a Union

GraphQL has two abstract output types to describe a field that can return multiple concrete object types: **interface** and **union**. Both let clients query polymorphic data, yet they express two different contracts. An interface defines a group of shared fields that every implementing object must provide; a union simply defines the set of object types that may appear in the result.

Choosing the right type helps the schema accurately express relationships between data types, helps clients write clear operations, and helps the server resolve the right object type at runtime. In Spring for GraphQL, SDL declares the interface/union, while GraphQL Java needs to determine the concrete type of the returned object through an appropriate type resolution mechanism.

This lesson explains criteria for choosing between an interface and a union, how clients query using inline fragments and __typename, how to configure runtime type resolvers in Spring for GraphQL, alternative design choices, and how to test them.

## 1. The Polymorphism Problem in GraphQL

Suppose an API has a search feature that returns books, authors, or publishers. Each result kind has its own fields:

~~~graphql
type Book {
  id: ID!
  title: String!
}

type Author {
  id: ID!
  name: String!
}

type Publisher {
  id: ID!
  companyName: String!
}
~~~

If three separate queries are declared, the client must know in advance which kind of result it wants to search:

~~~graphql
type Query {
  books(term: String!): [Book!]!
  authors(term: String!): [Author!]!
  publishers(term: String!): [Publisher!]!
}
~~~

This design makes sense if the three use cases are genuinely independent. However, if the requirement is unified search where a single result can be any of those kinds, the server needs a return type expressing multiple possibilities. An interface or union solves that problem.

The client can query a single field:

~~~graphql
type Query {
  search(term: String!): [SearchResult!]!
}
~~~

The rest of the schema defines **SearchResult** as a union or an interface depending on the relationship among the result types.

## 2. Interface: When Objects Share a Field Contract

An interface defines fields that multiple object types commit to providing. For example, books and authors both have an identifier:

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

type Query {
  node(id: ID!): Node
}
~~~

**Node** declares the shared field **id**. Every object implementing the interface must provide this field with a compatible type. **Book** and **Author** remain independent object types and can add their own fields.

Clients can query shared fields directly on the interface:

~~~graphql
query {
  node(id: "item-01") {
    id
    __typename
  }
}
~~~

If specific fields of a concrete type are needed, the client uses inline fragments:

~~~graphql
query {
  node(id: "item-01") {
    id
    ... on Book {
      title
    }
    ... on Author {
      name
    }
  }
}
~~~

The **id** field is queried directly because the interface guarantees every implementing type has that field. The **title** and **name** fields are selected only inside their corresponding fragments.

### An Interface Should Represent a Shared Concept

A good interface expresses a contract that is meaningful to clients, such as:

- **Node**: resources with a unified identifier.
- **Auditable**: objects carrying creation and update information.
- **SearchableItem**: results sharing common fields for search.
- **PaymentMethod**: payment methods sharing an identifier and a display name.

Do not create an interface merely because two objects happen to have a field with the same name. Check whether that field carries the same semantics and rules across types, and whether clients genuinely need to query it as part of a shared contract.

Example payment interface:

~~~graphql
interface PaymentMethod {
  id: ID!
  displayName: String!
}

type CardPayment implements PaymentMethod {
  id: ID!
  displayName: String!
  lastFourDigits: String!
}

type BankTransfer implements PaymentMethod {
  id: ID!
  displayName: String!
  bankName: String!
  accountReference: String!
}
~~~

Clients can retrieve **id** and **displayName** without knowing the concrete method, then select specific fields via fragments when needed.

## 3. Union: When Results Span Multiple Object Types Without a Shared Contract

A union defines a set of object types that can appear in a result. Unlike an interface, a union does not declare shared fields:

~~~graphql
union SearchResult = Book | Author | Publisher

type Query {
  search(term: String!): [SearchResult!]!
}
~~~

Clients cannot directly query **id**, **title**, or **name** on **SearchResult**, even if several members have fields with the same name. Clients must use inline fragments:

~~~graphql
query Search($term: String!) {
  search(term: $term) {
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
~~~

A union fits when heterogeneous results are grouped into a single use case without sharing a meaningful enough set of fields to form an interface. For example, search results might be books, authors, or publishers; they are all search results, yet they do not necessarily belong to a single domain concept outside that use case.

### Unions Contain Only Object Types

Union members must be object types. You cannot declare a scalar, enum, input object, interface, or another union as a member:

~~~graphql
union InvalidResult = Book | String
~~~

The declaration above is invalid because **String** is a scalar. If a result can take multiple data forms, wrap that data in separate object types and place those objects into the union.

## 4. Criteria for Choosing Interface vs. Union

The deciding factor is not the number of concrete types, but whether a meaningful shared field contract exists.

| Criterion | Interface | Union |
|---|---|---|
| Description | Shared field contract | Set of object types that can appear |
| Directly queryable fields | Fields declared on the interface | No shared fields declared by the union |
| Object-specific fields | Use inline fragments | Use inline fragments |
| Members | Object types implementing the interface | Object types listed in the union |
| Relationship between types | Share capabilities or properties | May be completely unrelated |
| Examples | PaymentMethod, Node | SearchResult, ActivityItem |
| Client needs concrete type | Use __typename or fragments | Typically use __typename and fragments |

You can use these questions to decide:

1. Do the types share one or more fields with the same business meaning?
2. Do clients need to query those shared fields without writing fragments?
3. Do the objects genuinely commit to the same capability, or do they merely happen to appear in the same result?
4. When adding a new type, can that type fully fulfill the shared field contract?
5. Do clients need to distinguish concrete types to render or handle them differently?

If a clear shared contract exists and clients need to rely on it, an interface is usually appropriate. If you only need to express "one of these object types," a union is usually clearer.

### Example: Sharing id Does Not Automatically Mean Using an Interface

Suppose search results consist of **Book**, **Author**, and **Publisher**. All three have an **id** field. You can create a **Node** interface if the API has a unified resource identifier concept and clients routinely need to query the shared ID.

If **id** is merely a technical field that happens to share a name, while the three types share no other behavior or meaning, a **SearchResult** union may still be the cleaner choice. With a union, clients query the ID inside each fragment. Do not create an interface just to avoid repeating a few lines of SDL if the shared contract adds no value for API consumers.

### Using Both Interfaces and Unions in the Same Schema

Interfaces and unions are not mutually exclusive. An object type can implement an interface while also being a member of one or more unions:

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

union SearchResult = Book | Author

type Query {
  node(id: ID!): Node
  search(term: String!): [SearchResult!]!
}
~~~

Here **Node** serves queries needing a unified identifier; **SearchResult** serves the unified search use case. The same object type can participate in both contracts.

## 5. Inline Fragments and __typename

Interfaces and unions are abstract types: an actual returned value is always a concrete object type. Clients use inline fragments to select fields by that type.

Example:

~~~graphql
query {
  search(term: "spring") {
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

**__typename** is a meta-field provided by GraphQL. It returns the concrete object type name at runtime, such as **Book** or **Author**. Clients commonly use this value to branch UI rendering or map results to concrete data types.

Example response:

~~~json
{
  "data": {
    "search": [
      {
        "__typename": "Book",
        "id": "book-01",
        "title": "Spring GraphQL"
      },
      {
        "__typename": "Author",
        "id": "author-01",
        "name": "An Nguyen"
      }
    ]
  }
}
~~~

With an interface, shared fields can be selected outside fragments:

~~~graphql
query {
  searchableItems {
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
~~~

With a union, there are no shared fields to select outside fragments:

~~~graphql
query {
  search(term: "spring") {
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

### Fragments Can Be Named and Reused

When multiple operations need the same selection set, clients can declare named fragments:

~~~graphql
fragment BookFields on Book {
  id
  title
}

fragment AuthorFields on Author {
  id
  name
}

query Search($term: String!) {
  search(term: $term) {
    __typename
    ...BookFields
    ...AuthorFields
  }
}
~~~

A fragment is applied only when the runtime object matches the type condition. GraphQL skips fragments that do not match the concrete object type.

## 6. What Is Runtime Type Resolution?

A schema declaring an interface or union only describes which concrete types may appear. When a resolver returns a Java object, GraphQL Java still needs to know which object type in the schema that object corresponds to.

For example, a search resolver returns:

- A Java instance of **Book**.
- A Java instance of **Author**.
- A Java instance of **Publisher**.

The field in SDL has type **SearchResult**, yet the runtime must determine whether each value is a **Book**, **Author**, or **Publisher**. That job is called **type resolution**.

You can visualize the flow:

~~~mermaid
flowchart TD
    Q[Query.search resolver] --> L[List of Java objects]
    L --> T{TypeResolver}
    T -->|Book instance| B[GraphQL object type Book]
    T -->|Author instance| A[GraphQL object type Author]
    T -->|Publisher instance| P[GraphQL object type Publisher]
    B --> F[Resolve fragment fields]
    A --> F
    P --> F
    F --> R[GraphQL response]
~~~

If GraphQL cannot determine the object type, the operation may raise an execution error when resolving the abstract type. Thus, declaring the union/interface in SDL and returning the right Java object types are two pieces that must be connected together.

## 7. Configuring TypeResolver in Spring for GraphQL

Spring for GraphQL uses GraphQL Java runtime wiring. You can register a **TypeResolver** for an interface or union via **RuntimeWiringConfigurer**.

Example schema:

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
  search(term: String!): [SearchResult!]!
}
~~~

Resolver returning Java objects:

~~~java
@Controller
public class SearchController {

    private final SearchService searchService;

    public SearchController(SearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    public List<Object> search(@Argument String term) {
        return searchService.search(term);
    }
}
~~~

Runtime wiring can determine the object type from the Java type:

~~~java
@Configuration
public class GraphQlTypeResolverConfiguration {

    @Bean
    RuntimeWiringConfigurer runtimeWiringConfigurer() {
        return wiringBuilder -> wiringBuilder.type(
                TypeRuntimeWiring.newTypeWiring("SearchResult")
                        .typeResolver(environment -> {
                            Object source = environment.getObject();

                            if (source instanceof Book) {
                                return environment.getSchema()
                                        .getObjectType("Book");
                            }
                            if (source instanceof Author) {
                                return environment.getSchema()
                                        .getObjectType("Author");
                            }

                            throw new IllegalStateException(
                                    "Unsupported SearchResult type: "
                                            + source.getClass().getName());
                        }));
    }
}
~~~

In this example, **TypeRuntimeWiring** attaches the type resolver to the **SearchResult** union. The resolver reads the source object, checks the Java type, and returns the corresponding **GraphQLObjectType** in the schema.

If a field returns an interface, register the type resolver for the interface name in the same way. An object type can implement multiple interfaces; each abstract type needs an appropriate way to determine the concrete type.

This is an illustrative example of schema-first runtime wiring. GraphQL type names must match the SDL, and Java classes must be replaced with the application's actual data types. If using the default type resolution mechanism or **isTypeOf** on object types, an explicit resolver may not be required; verify the application's runtime wiring behavior before adding configuration.

### Do Not Confuse TypeResolver with Field Resolvers

The two mechanisms have distinct responsibilities:

| Mechanism | Question Answered |
|---|---|
| TypeResolver | Which concrete GraphQL object type does this Java object belong to? |
| DataFetcher / @SchemaMapping | What is the value of the field being queried? |

For example, **TypeResolver** determines that the source object is a **Book**. Only then does a field resolver or property data fetcher retrieve **Book.title** or other relational fields.

Do not place data-loading logic inside a TypeResolver. A type resolver should determine the object type from data already present, while fetching data belongs to resolvers or services.

## 8. Field Resolvers on Objects Implementing an Interface

Once GraphQL knows the concrete type, the object's fields are resolved according to their corresponding mappings. Spring for GraphQL supports **@SchemaMapping** to map specific fields:

~~~graphql
interface SearchableItem {
  id: ID!
}

type Book implements SearchableItem {
  id: ID!
  title: String!
  author: Author
}

type Author implements SearchableItem {
  id: ID!
  name: String!
}
~~~

The controller can implement both the root field and relational fields:

~~~java
@Controller
public class CatalogController {

    private final CatalogService catalogService;
    private final AuthorService authorService;

    public CatalogController(
            CatalogService catalogService,
            AuthorService authorService) {
        this.catalogService = catalogService;
        this.authorService = authorService;
    }

    @QueryMapping
    public List<Object> searchableItems() {
        return catalogService.findSearchableItems();
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }
}
~~~

The **id** field can be supplied from a property of the source object if a suitable getter exists. The **author** field needs its own resolver because it must load the author from a service.

If many Books need to load their Authors at once, a per-source resolver can cause N+1 queries. You can use **@BatchMapping** or DataLoader to batch data loading. Choosing an interface or union does not by itself solve N+1; that is a data-fetching strategy concern.

## 9. When NOT to Use an Interface or Union

Not every case with multiple variants or states requires an abstract type.

### Use an Enum When Only Representing a Status

If a field only has simple classification values, an enum is usually a better fit:

~~~graphql
enum OrderStatus {
  NEW
  PROCESSING
  SHIPPED
  CANCELLED
}

type Order {
  id: ID!
  status: OrderStatus!
}
~~~

There is no need to create a union of **NewOrder**, **ShippedOrder**, and **CancelledOrder** objects if the states differ only by an enum value and share the same data structure.

### Use a Regular Object Type When Structure Is Stable

If a field always returns the same structure, use a concrete object type:

~~~graphql
type Money {
  amount: Float!
  currency: String!
}

type Product {
  id: ID!
  price: Money!
}
~~~

There is no need for a union just because values have multiple currencies. Currency is data belonging to the **Money** object, not a different object type.

### Use a Wrapper Object When Shared Metadata Is Needed

Sometimes heterogeneous results have no shared fields, yet the API needs extra information about each result such as ranking score, data source, or match timestamp. You can wrap the union inside an object:

~~~graphql
union SearchItem = Book | Author

type SearchHit {
  score: Float!
  source: String!
  item: SearchItem!
}

type Query {
  search(term: String!): [SearchHit!]!
}
~~~

Clients can query shared metadata on **SearchHit**, then use fragments on **item**:

~~~graphql
query {
  search(term: "spring") {
    score
    source
    item {
      __typename
      ... on Book {
        title
      }
      ... on Author {
        name
      }
    }
  }
}
~~~

A wrapper object is useful when the metadata belongs to the search hit rather than to Book or Author. It also avoids adding unrelated fields to each object type.

## 10. Interfaces and Unions Are Only Used in Output Positions

Interfaces and unions are output types. They can be the return type of a field, but they cannot be used as the type of an argument or a field of an input object.

The following example is invalid:

~~~graphql
input CreateActivityInput {
  target: SearchResult
}
~~~

If the client needs to send one of several data forms, you can use one of these approaches:

- An input object with a discriminator such as **kind** and corresponding input fields.
- Separate mutations for each action type.
- A general input object containing the ID of an existing resource, after which the server determines the type from data.

Example input with a discriminator:

~~~graphql
enum ActivityTargetKind {
  BOOK
  AUTHOR
}

input CreateActivityInput {
  targetKind: ActivityTargetKind!
  targetId: ID!
}

type Mutation {
  createActivity(input: CreateActivityInput!): Activity!
}
~~~

The server verifies whether the target ID and target kind match an actual object. Never trust a client-sent discriminator while skipping authorization or resource-type checks.

## 11. Schema Evolution When Using Interfaces and Unions

Abstract types establish a contract for clients, so changing members or fields can affect generated code and client branching logic.

| Change | Impact to Consider |
|---|---|
| Add field to interface | All implementing objects must provide a compatible field; clients can start querying the new field |
| Add object implementing interface | Clients may receive a new type; branching logic needs a fallback branch |
| Add member to union | Clients may receive a new object type and need to handle its fragment |
| Remove member from union | Fragments and client code targeting that type may become invalid or obsolete |
| Rename interface/union | Operations referencing the type condition or return field may become invalid |
| Change shared field | Can affect all clients querying the interface |

When adding a new member to a union, clients should not assume the list of types is immutable. Use **__typename** and include a fallback branch when receiving an unknown type. For clients using code generation, check the configuration for handling unknown types or the strategy for updating generated models.

When adding a field to an interface, all implementing objects must satisfy the new contract. If objects cannot provide that field with the same meaning, the field may not belong on the interface; consider fragments on concrete types or a smaller interface.

## 12. Security with Interfaces and Unions

Having an object type implement an interface or belong to a union does not automatically grant user access permissions. Authorization must still be checked per object and per field.

Example:

~~~graphql
interface Account {
  id: ID!
  displayName: String!
}

type PersonalAccount implements Account {
  id: ID!
  displayName: String!
  personalEmail: String
}

type BusinessAccount implements Account {
  id: ID!
  displayName: String!
  taxCode: String!
}
~~~

A user might be allowed to view **displayName** but not **personalEmail** or **taxCode**. Resolvers for sensitive fields must verify appropriate permissions. Clients use fragments solely to select fields; fragments are not a security mechanism.

With unions, each member may have different security policies. The server must ensure the query returns only objects the user is permitted to see, while also checking permissions for child fields. Do not check permissions only at the root search and assume every field on the results is public.

## 13. Testing Interfaces and Unions

GraphQlTester can verify both concrete types and fields inside fragments. Example query:

~~~graphql
query Search($term: String!) {
  search(term: $term) {
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

Testing concrete types:

~~~java
graphQlTester.document("""
        query {
            search(term: "spring") {
                __typename
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
    .path("search[0].__typename")
    .entity(String.class)
    .isEqualTo("Book");
~~~

What to test:

1. Resolvers return the expected Java object types declared in the interface/union.
2. TypeResolver maps each object to the right GraphQL object type.
3. Unknown Java types are handled deliberately rather than silently returning the wrong type.
4. Clients querying shared interface fields directly succeed.
5. Inline fragments return fields only when the object type matches.
6. Unions disallow querying fields directly outside fragments, except supported meta-fields.
7. **__typename** returns the exact concrete object type name.
8. Specific field resolvers for each object type are invoked properly.
9. Authorization is enforced for sensitive fields on each member.
10. Adding a new member does not break existing clients or mappings.

Beyond execution tests, you can validate the schema on application startup to catch objects that fail to fully implement an interface or unions referencing invalid types.

## 14. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using a union despite a significant shared field contract | Clients must repeat fragments for shared fields | Consider an interface |
| Using an interface just because field names match | Shared contract lacks domain meaning | Confirm shared semantics before creating an interface |
| Querying fields directly on a union | Invalid operation | Use inline fragments |
| Putting a scalar or interface into a union | Invalid schema | List only object types |
| Declaring an interface without proper type resolution | Runtime cannot determine concrete objects | Configure TypeResolver or an equivalent mechanism |
| Confusing TypeResolver with @SchemaMapping | Mixes type identification with field fetching | Separate the responsibilities of both mechanisms |
| Failing to handle new types on the client | UI or generated client may error when a member is added | Use __typename and a fallback |
| Relying on fragments for authorization | Clients can bypass the fragment and request another field | Enforce permissions on the server |
| Using abstract types for input data | Invalid SDL | Design an input object with a discriminator or separate mutations |
| Using a union to represent simple states | Unnecessary schema complexity | Use an enum or a regular object |

## 15. Workflow for Choosing Interface vs. Union

When designing a field that can return multiple object types, follow these steps:

1. List the concrete object types that can actually appear.
2. Find common fields and check whether they share the same business meaning.
3. If there is a useful shared contract for clients, define an interface.
4. If you only need a set of heterogeneous result types, define a union.
5. If only representing a status or simple classification, consider an enum.
6. If shared metadata is needed for polymorphic results, consider a wrapper object containing the interface/union.
7. Design inline fragments and __typename usage for clients.
8. Configure type resolution to map Java objects to GraphQL object types.
9. Keep field resolvers, authorization, and batch loading within their proper responsibilities.
10. Test every concrete type and prepare for adding future members.

Interfaces and unions both help GraphQL model polymorphic data, yet their purposes differ. An interface fits when objects share a meaningful field contract; a union fits when an API needs to return one of several object types without imposing shared fields. In Spring for GraphQL, SDL defines the contract, TypeResolver determines the concrete type at runtime, and resolvers supply field values. Choosing according to data semantics and client needs makes schemas clearer, easier to evolve, and easier to test.
