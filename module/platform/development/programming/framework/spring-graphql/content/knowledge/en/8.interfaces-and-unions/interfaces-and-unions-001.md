# Interfaces in Schema

In GraphQL, clients often need to query objects that share some common properties while still having type-specific data. For example, a catalog system might manage books, authors, and magazines. All of them have an identifier and a display name, but a book has a title and an ISBN, an author has a biography, and a magazine has an issue number. If only separate object types are used, the client must know each type in advance to select fields. **Interfaces** allow a schema to define a shared field contract that multiple object types implement together.

An interface is an abstract output type in GraphQL. It describes the fields that every implementing object type must provide. When a field in a schema returns an interface, the actual value at execution time is still a concrete object type. This enables an API to expose a common return type while preserving the specialized data of each object kind.

In Spring for GraphQL, interfaces are declared using SDL, concrete Java objects are returned by resolvers, and the GraphQL runtime determines the corresponding object type during execution. For an interface or union, mapping a Java object to a GraphQL object type is performed through a **TypeResolver**, which can be registered using a **RuntimeWiringConfigurer**.

## Declaring an Interface in SDL

Use the **interface** keyword to declare an interface and its list of shared fields:

~~~graphql
interface CatalogItem {
  id: ID!
  name: String!
}

type Book implements CatalogItem {
  id: ID!
  name: String!
  title: String!
  isbn: String
}

type Author implements CatalogItem {
  id: ID!
  name: String!
  biography: String
}

type Magazine implements CatalogItem {
  id: ID!
  name: String!
  issueNumber: Int!
}
~~~

In this example:

- **CatalogItem** is the interface, defining two shared fields, id and name.
- **Book**, **Author**, and **Magazine** are the object types implementing the interface.
- Each object type must declare the interface's fields with compatible types.
- Each object type can add its own fields, such as isbn, biography, or issueNumber.

The **implements** keyword indicates that an object type commits to fulfilling the interface's contract. The schema does not create an object named CatalogItem to store data; it uses the interface as an abstract type to describe the concrete objects that may be returned.

## Interface as a Shared Field Contract

Clients can query fields declared on the interface directly without needing to know which concrete type the actual object is:

~~~graphql
type Query {
  catalogItem(id: ID!): CatalogItem
  catalogItems: [CatalogItem!]!
}
~~~

The following operation works with every object type that implements CatalogItem:

~~~graphql
query Catalog {
  catalogItems {
    id
    name
  }
}
~~~

Because id and name are part of the interface's contract, GraphQL knows that Book, Author, and Magazine can all return these two fields. The client can write a single shared query to display the catalog list.

An interface only exposes the intersection among implementing types. If a client needs a Book-specific field, such as isbn, it cannot select that field directly on CatalogItem. The client must use an inline fragment with the type condition on Book. This is how GraphQL keeps the shared contract stable while still allowing access to specialized data.

## Rules When an Object Type Implements an Interface

The schema must guarantee that an object type genuinely satisfies the interface contract. Some important rules:

1. **All interface fields must be present.** If CatalogItem declares id and name, every implementing object type must include both fields.
2. **Output types must be compatible.** An object's field must have the same type or a valid subtype of the type declared on the interface. For example, if an interface returns an interface or union, the object can return an appropriate concrete object type.
3. **Declared arguments must be preserved.** The object type must provide the interface field's arguments with the same names and types.
4. **No new required arguments may be added.** An object can add optional arguments or arguments with default values, but it must not force clients to supply extra arguments that the interface contract does not require.
5. **Additional specific fields may be added.** Fields not present in the interface are allowed to be declared on the concrete object type.

Example of an interface with an argument:

~~~graphql
interface CatalogItem {
  id: ID!
  name: String!
  relatedItems(limit: Int = 10): [CatalogItem!]!
}

type Book implements CatalogItem {
  id: ID!
  name: String!
  relatedItems(limit: Int = 10): [CatalogItem!]!
  isbn: String
}
~~~

Book must keep the limit argument with type Int and a default value compatible with the contract. If Book additionally declares language: String, this is an optional argument, so clients calling through the interface are not required to pass it. If Book adds region: String! without a default value, the implementation requires information that the client does not know from the interface contract; the schema is invalid.

These rules allow clients to write queries based on the interface without knowing the details of each implementation. If an implementation changes a field or argument incompatibly, schema validation will catch the issue before the application serves operations.

## Interface as an Output Type

An interface can be used as the return type of a field, including Query, Mutation, Subscription, or nested fields. It can also be wrapped in lists and non-null types:

~~~graphql
type Query {
  item(id: ID!): CatalogItem
  items: [CatalogItem!]!
}

type Mutation {
  renameItem(id: ID!, name: String!): CatalogItem
}
~~~

An interface is not an input type. You cannot declare an argument like find(item: CatalogItem) or an input object with a field of type CatalogItem. If you need to receive data from a client, define a separate input object type with appropriate scalars, enums, or input objects. Separating input and output keeps the API contract clear and prevents clients from sending internal objects that the server does not want to accept.

## Querying Shared Fields and Specific Fields

For a field returning an interface, clients can select shared fields directly and use inline fragments for type-specific fields:

~~~graphql
query Catalog {
  catalogItems {
    id
    name
    __typename
    ... on Book {
      title
      isbn
    }
    ... on Author {
      biography
    }
    ... on Magazine {
      issueNumber
    }
  }
}
~~~

**__typename** is a meta-field provided by GraphQL that indicates the actual object type of each element. Inline fragments restrict the selected fields by concrete type. If an element is a Book, the response includes title and isbn; if it is an Author, the response includes biography.

Example response:

~~~json
{
  "data": {
    "catalogItems": [
      {
        "id": "book-101",
        "name": "Spring in Action",
        "__typename": "Book",
        "title": "Spring in Action",
        "isbn": "9781617297571"
      },
      {
        "id": "author-12",
        "name": "Craig Walls",
        "__typename": "Author",
        "biography": "Software developer and author"
      }
    ]
  }
}
~~~

An inline fragment does not filter elements out of the list. It only determines which fields are resolved for each object. If the client needs to filter the list by type, provide an argument or a search field with explicit filtering rules.

## Mapping an Interface to Java in Spring for GraphQL

SDL describes the interface and object types; on the Java side, you can use an interface to represent the shared contract:

~~~java
public interface CatalogItem {
    String id();
    String name();
}

public record Book(
        String id,
        String name,
        String title,
        String isbn) implements CatalogItem {
}

public record Author(
        String id,
        String name,
        String biography) implements CatalogItem {
}

public record Magazine(
        String id,
        String name,
        int issueNumber) implements CatalogItem {
}
~~~

A service can return a concrete implementation or a collection of implementations:

~~~java
public interface CatalogService {
    CatalogItem findById(String id);
    List<CatalogItem> findAll();
}
~~~

The controller maps the Query root fields:

~~~java
@Controller
public class CatalogController {

    private final CatalogService catalogService;

    public CatalogController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @QueryMapping
    public CatalogItem catalogItem(@Argument String id) {
        return catalogService.findById(id);
    }

    @QueryMapping
    public List<CatalogItem> catalogItems() {
        return catalogService.findAll();
    }
}
~~~

When catalogItem returns a Book, GraphQL needs to know that this object corresponds to the GraphQL object type Book; when it returns an Author, the runtime needs to identify the Author type. This is especially important because the declared return type is CatalogItem, not a concrete object type.

## Registering a TypeResolver

GraphQL Java uses a TypeResolver to determine the actual object type for an interface. Spring for GraphQL provides **ClassNameTypeResolver**, which supports mapping Java classes to object type names in SDL.

Example of explicit mapping configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.ClassNameTypeResolver;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlTypeConfiguration {

    @Bean
    RuntimeWiringConfigurer catalogItemTypeResolver() {
        ClassNameTypeResolver typeResolver = new ClassNameTypeResolver();
        typeResolver.addMapping(Book.class, "Book");
        typeResolver.addMapping(Author.class, "Author");
        typeResolver.addMapping(Magazine.class, "Magazine");

        return builder -> builder.type(
                "CatalogItem",
                typeWiring -> typeWiring.typeResolver(typeResolver)
        );
    }
}
~~~

RuntimeWiringConfigurer is discovered by Spring Boot when initializing the GraphQL runtime. The configuration above attaches the type resolver to the CatalogItem interface. When GraphQL receives a Java object of class Book, Author, or Magazine, the resolver returns the corresponding object type in the schema.

The name in addMapping must match the SDL object type name. If the class name already follows the convention and does not have a package or suffix that alters the GraphQL name, you can use the default rules of ClassNameTypeResolver; explicit mapping makes the schema more stable when Java class names differ from the public API names.

If more complex rules are needed, you can implement graphql.schema.TypeResolver directly. The resolver receives a TypeResolutionEnvironment, inspects the source object, and returns the appropriate GraphQLObjectType. You should not rely on an arbitrary property or an unstable class name if the domain has multiple implementations or proxies.

## Interface Fields and @SchemaMapping

Fields declared on an interface are part of the shared contract. Implementing object types can obtain values from default property accessors if the Java object has the corresponding property. When a field needs to query data or execute logic, Spring for GraphQL allows declaring a resolver using @SchemaMapping.

Example of an interface with a relatedItems field:

~~~graphql
interface CatalogItem {
  id: ID!
  name: String!
  relatedItems: [CatalogItem!]!
}
~~~

Resolvers can handle the field on the source objects implementing the interface:

~~~java
@Controller
public class CatalogItemController {

    private final CatalogService catalogService;

    public CatalogItemController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @SchemaMapping(typeName = "Book", field = "relatedItems")
    public List<CatalogItem> relatedItemsForBook(Book book) {
        return catalogService.findRelated(book.id());
    }

    @SchemaMapping(typeName = "Author", field = "relatedItems")
    public List<CatalogItem> relatedItemsForAuthor(Author author) {
        return catalogService.findRelated(author.id());
    }
}
~~~

Here the relatedItems field is mapped separately for two concrete object types. Both methods can call the same shared service, but each resolver receives the appropriately typed source object. For fields with existing property accessors, GraphQL can read the value directly without a resolver. For fields that require querying data, register data fetchers on the concrete object types and test operations for each implementation to make sure the field resolves properly.

## An Interface Can Be Implemented by Multiple Types

An object type can implement multiple interfaces. For example, a content item in a system can be both identifiable as a Node and have update timestamp information:

~~~graphql
scalar DateTime

interface Node {
  id: ID!
}

interface Auditable {
  createdAt: DateTime!
  updatedAt: DateTime!
}

type Book implements Node & Auditable {
  id: ID!
  createdAt: DateTime!
  updatedAt: DateTime!
  title: String!
}
~~~

Book must satisfy the contracts of both Node and Auditable. Clients can query shared fields through the corresponding interface, while the title field remains only on Book. Multiple interfaces are useful when domain concepts share independent sets of behaviors.

GraphQL also supports interfaces implementing other interfaces in compatible schema/runtime versions. When using this capability, ensure that the GraphQL Java version managed by Spring Boot supports the corresponding syntax and rules; the final object type must still implement all required fields from every interface in the inheritance chain.

## How Are Interfaces and Unions Different?

Interfaces and unions are both abstract output types, but they describe contracts differently:

| Criterion | Interface | Union |
| --- | --- | --- |
| Shared fields | Has fields declared in the interface | Declares no shared business fields |
| Object members | Object types implement via implements | Object types are listed in the union definition |
| Querying fields | Select shared fields directly; use fragments for specific fields | Use inline fragments to select fields of each object |
| Purpose | Represent objects sharing a common contract | Group heterogeneous objects into a single result |

Choose an interface when types share a meaningful set of fields in the domain. Choose a union when you need to represent multiple result types without a significant shared field contract. Do not create an interface just to force unrelated types to share a superficial field.

## Common Mistakes When Implementing Interfaces

Some common mistakes when building schemas and resolvers:

- An object type is missing a required interface field or declares an incompatible field type.
- An object type drops an interface argument, changes an argument's type, or adds a new required argument.
- Using an interface as an input argument or a field of an input object.
- A resolver returns a Java class that has no mapping to a concrete GraphQL object type.
- A type resolver returns an object type name that does not exist or does not belong to the interface's implementations.
- A client selects an implementation-specific field directly on the interface without using an inline fragment.
- A shared field is declared on the interface, but the resolver or property accessor does not provide the corresponding value.

When debugging, check in order: whether the SDL is valid; whether the object type fulfills the full contract; which Java class the resolver returns; whether TypeResolver maps that class properly; and finally whether the operation uses fragments for specific fields. You can add __typename to the query to observe the concrete type that the runtime is returning.

## Security and Performance

Interfaces let clients query multiple object types through a shared contract, but they do not automatically create shared access permissions for every implementation. A user might be permitted to read Book but not Author in certain contexts. Enforce permissions in resolvers, services, or the data access layer per object and per field. Do not expose sensitive fields on an interface if every implementation cannot guarantee the same access policy.

Nested fields on an interface can also cause N+1 issues. For example, a query returning many CatalogItem instances and then fetching relatedItems for each element may trigger a separate query per item. Spring for GraphQL supports @BatchMapping and DataLoader to batch related loads. Design actual batch queries in the repository/service layer, paginate lists, and limit operation depth or complexity.

When testing, create data for each implementing object type and verify:

- Queries for shared fields work across all implementations.
- Queries for specific fields appear only in fragments of the matching type.
- __typename returns the exact object type name.
- Resolvers and type resolvers handle each implementation properly.
- Access permissions are enforced per data type.
- Batch loading works when querying lists of multiple objects.

An interface is how GraphQL describes a shared output contract for multiple object types. In Spring for GraphQL, SDL defines the contract, Java models represent the implementations, controllers and services supply the data, and TypeResolver helps the runtime identify the actual object type. When these pieces are consistent, clients can build flexible queries while clearly understanding the shared and specific fields of each data type.
