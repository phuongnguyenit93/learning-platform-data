# Object type

Object types are the core data types used to describe an object that a GraphQL API can return to a client. Each object type defines a set of fields with names, return types, and optional arguments. When a client queries a field that returns an object type, the client continues by selecting the nested subfields it needs.

In Spring for GraphQL, object types are typically declared using SDL, while the value of each field is provided by a data fetcher or resolver. Spring supports mapping Java methods to fields using annotations such as **@QueryMapping** and **@SchemaMapping**. For fields that can be read directly from properties of the source object, GraphQL Java can also use the default property data fetcher.

This lesson focuses on how to design object types, how fields form nested data structures, how arguments work, the relationship between object types and Java classes, and how to implement resolvers in Spring for GraphQL.

## 1. Object types describe the shape of output data

An object type is declared using the **type** keyword in SDL:

~~~graphql
type Book {
  id: ID!
  title: String!
  publishedAt: String
}
~~~

The declaration above creates an object type named **Book** with three fields:

- **id** has type **ID!**, meaning the returned value must be non-null.
- **title** has type **String!**, meaning the title must always have a value.
- **publishedAt** has type **String**, meaning the value can be null.

An object type defines the contract that clients are allowed to read. It is not a concrete instance, not a database query statement, and does not automatically create a Java object. The server needs logic to provide values for the fields when an operation is executed.

An object type can be viewed as a structural description:

~~~mermaid
classDiagram
    class Book {
        ID id
        String title
        String publishedAt
    }
~~~

This diagram only illustrates the fields in the schema. GraphQL types and Java types can be mapped to one another, but they are not required to have identical structures or names.

## 2. Fields of an object type

Each field in an object type has a name and an output type. General syntax:

~~~graphql
type TypeName {
  fieldName: OutputType
}
~~~

An object type can contain several categories of output types:

- Scalars such as **String**, **Int**, **Float**, **Boolean**, and **ID**.
- Enums such as **BookStatus**.
- Other object types such as **Author** or **Review**.
- Interfaces or unions when a field can return one of multiple object types.
- Wrapped list and non-null types such as **[Book!]!**.

Example:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Book {
  id: ID!
  title: String!
  price: Float!
  status: BookStatus!
  tags: [String!]!
  publisher: Publisher
}

type Publisher {
  id: ID!
  name: String!
}
~~~

In this example, **Book** has scalar, enum, and list fields, as well as a relation to another object type. The **publisher** field is nullable because a book might not have a publisher assigned yet. The **tags** field always returns a list, and every element in the list must be non-null.

### Field names and naming conventions

GraphQL is case-sensitive. By common convention:

- Object types use PascalCase, such as **Book**, **BookReview**.
- Fields use camelCase, such as **publishedAt**, **averageRating**.
- Field names should clearly express the data or action.
- Avoid overly generic names such as **value**, **data**, or **info** without specific context.
- Do not name types or fields starting with two underscores; this prefix is reserved for GraphQL's introspection system, such as the **__typename** meta-field.

An object type can also implement one or more interfaces and can be a member of a union. When implementing an interface, the object must provide the fields required by the interface with compatible types:

~~~graphql
interface Node {
  id: ID!
}

type Book implements Node {
  id: ID!
  title: String!
}
~~~

In this example, **Book** remains a concrete object type; **Node** only describes a shared field contract.

You should not arbitrarily rename public fields once clients are using the API. Renaming a field is equivalent to removing the old field and adding a new one, which can invalidate existing client operations. When a replacement is needed, you can add the new field, mark the old field with **@deprecated**, and remove it after an appropriate transition period.

### Describing objects and fields

SDL supports descriptions using string literals placed immediately before a type or field definition:

~~~graphql
"""
A book title provided by the catalog service.
"""
type Book {
  "Unique identifier of the book."
  id: ID!

  "Display title shown to readers."
  title: String!

  "Timestamp when the book was published."
  publishedAt: String
}
~~~

Descriptions make the schema easier to explore in GraphiQL, IDEs, and introspection tools. Write descriptions explaining business semantics, units of measurement, nullability rules, or usage conditions when those details are not obvious from the field name.

## 3. Root object types

GraphQL root operation types are also object types. They are the entry points for each operation:

~~~graphql
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Mutation {
  createBook(title: String!): Book!
}

type Subscription {
  bookPublished: Book!
}
~~~

Here:

- **Query** provides fields for reading data.
- **Mutation** provides fields for modifying data.
- **Subscription** provides fields that produce update streams.

A GraphQL schema must have a root Query. Root Mutation and root Subscription are optional. Whether a type is a root type or a nested object type, it follows the same rules for fields and output types.

Clients do not query type names directly. A client starts from a root field and selects subsequent fields in a selection set:

~~~graphql
query {
  book(id: "book-01") {
    id
    title
  }
}
~~~

In the operation above, **book** is a field on **Query**; its result has type **Book**. The inner selection set picks two fields from the resulting object.

## 4. Object fields can accept arguments

A field can declare arguments so clients can pass parameters for fetching data. Syntax:

~~~graphql
type TypeName {
  fieldName(argumentName: InputType): OutputType
}
~~~

Example:

~~~graphql
type Book {
  id: ID!
  title: String!
  reviews(first: Int = 10): [Review!]!
}

type Review {
  id: ID!
  rating: Int!
  content: String
}
~~~

The **reviews** field accepts a **first** argument to limit the number of reviews returned. Clients can use the default value or pass another value:

~~~graphql
query {
  book(id: "book-01") {
    title
    reviews(first: 3) {
      rating
      content
    }
  }
}
~~~

Arguments can be scalars, enums, or input objects. Object types, interfaces, and unions are not input types, so they cannot be used directly as argument types. If you need to send multiple filter criteria, create a dedicated input object.

Example:

~~~graphql
enum ReviewSort {
  NEWEST
  HIGHEST_RATING
}

input ReviewFilter {
  minimumRating: Int
  containsText: String
}

type Book {
  id: ID!
  reviews(
    filter: ReviewFilter
    sort: ReviewSort = NEWEST
    first: Int = 10
  ): [Review!]!
}
~~~

When designing arguments, consider:

- Is the value required, or can it have a default?
- Does a null value mean something different from omitting the argument?
- Are min/max bounds needed for the result count?
- Is cursor-based pagination needed instead of just offset or count?
- Can related fields share an input object, or do they need separate inputs?

GraphQL validates argument types and presence against the schema, but business validation such as capping **first** at 100 still needs to be enforced on the server.

## 5. Relationships between object types

An object type can reference another object type as a field's return type. This enables the schema to describe nested relationships that clients can select as needed.

Example of a catalog with books, authors, and publishers:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author!
  publisher: Publisher
}

type Author {
  id: ID!
  name: String!
  books: [Book!]!
}

type Publisher {
  id: ID!
  name: String!
  books: [Book!]!
}
~~~

Clients can retrieve multiple levels of data in a single operation:

~~~graphql
query {
  book(id: "book-01") {
    id
    title
    author {
      id
      name
    }
    publisher {
      name
    }
  }
}
~~~

GraphQL returns a data structure matching the selection set. A client can select only **title**, or also fetch **author.name** and **publisher.name** without requiring the server to build a separate endpoint for every combination of fields.

Relationships in the schema do not have to mirror database relationships verbatim. For instance, the database might have a join table between books and authors, while the schema exposes only an **author** field. Conversely, a field like **recommendedBooks** can be aggregated from multiple data sources without existing as a direct relationship in the database.

### One-to-one and one-to-many relationships

A one-to-one or many-to-one relationship is typically represented by a single object field:

~~~graphql
type Book {
  author: Author!
}
~~~

A one-to-many relationship is typically represented by a list:

~~~graphql
type Author {
  books: [Book!]!
}
~~~

The schema only expresses the shape of the data. It does not guarantee that resolvers load data efficiently. If a query fetches 50 authors and each author queries the database separately for books, the server can trigger an N+1 query problem. In that case, consider batch loading, DataLoader, or **@BatchMapping**.

### Recursive relationships

An object type can reference itself:

~~~graphql
type Category {
  id: ID!
  name: String!
  parent: Category
  children: [Category!]!
}
~~~

This pattern works well for category trees, directories, organizations, or hierarchical structures. The schema allows clients to query nested levels:

~~~graphql
query {
  category(id: "root") {
    name
    children {
      name
      children {
        name
      }
    }
  }
}
~~~

A recursive schema does not mean an operation can run infinitely on its own. A GraphQL operation is a finite document with a finite selection set. However, clients can send deeply nested queries or repeat fields across many branches, driving up execution cost. The server should enforce query depth limits, complexity limits, or appropriate resource-limiting policies.

## 6. Selection sets and how clients read objects

When a field returns a scalar or enum, the client selects that field directly. When a field returns an object, the client must specify a selection set for that object:

~~~graphql
query {
  book(id: "book-01") {
    title
  }
}
~~~

The example above is valid because **title** is a scalar field. If the client writes:

~~~graphql
query {
  book(id: "book-01")
}
~~~

the operation is invalid because **book** returns a **Book** object, yet the client did not specify which subfields to fetch.

Similarly, a client cannot write a selection set on a scalar:

~~~graphql
query {
  book(id: "book-01") {
    title {
      value
    }
  }
}
~~~

This operation is invalid because **title** is a **String**, not an object type.

The selection set rule gives GraphQL responses an explicit structure: each object in the result contains only the fields requested by the client. This is an important characteristic when designing object types, because the field structure is the exact data surface clients can discover and consume.

### Aliases and fragments when querying objects

Clients can use aliases when they need to fetch the same field with different arguments in one operation:

~~~graphql
query {
  book(id: "book-01") {
    title
    latestReviews: reviews(first: 3) {
      rating
    }
    topReviews: reviews(sort: HIGHEST_RATING, first: 3) {
      rating
    }
  }
}
~~~

Fragments help reuse selection sets for object types:

~~~graphql
fragment BookSummary on Book {
  id
  title
  status
}

query {
  books {
    ...BookSummary
  }
}
~~~

Aliases and fragments belong to the client operation language; they do not alter the object type definition on the server.

## 7. Object types and input types are distinct concepts

Object types describe data returned by the server. Input objects describe data clients are allowed to send in. These two categories have different rules:

| Characteristic | Object type | Input object |
|---|---|---|
| SDL keyword | **type** | **input** |
| Usage position | Field return type | Argument or input variable |
| Can contain other object fields | Yes | No |
| Can contain interface/union | Allowed as return type | No |
| Can contain scalars and enums | Yes | Yes |
| Can contain list/non-null | Yes | Yes |

Example:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author!
}

input CreateBookInput {
  title: String!
  authorId: ID!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

You cannot use **Book** as an argument type just because Java has a Book class. If you need to send data to create a book, define a separate input object. This allows the API to control exactly which fields clients are permitted to send and avoids exposing internal attributes.

You do not necessarily need a one-to-one input object for every object type. Input and output often serve different purposes. For example, **Book** has **id**, **createdAt**, **author**, and **internalStatus**, whereas **CreateBookInput** only accepts **title** and **authorId**.

## 8. Object types are not synonymous with Java classes or database entities

An object type is a GraphQL schema concept. A Java class, record, DTO, or entity is an application data type. A database table or document is a storage structure. They can be mapped to each other, but they should not be conflated.

Example public schema:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author!
}
~~~

The internal Java model may contain additional data:

~~~java
public class Book {
    private String id;
    private String title;
    private String authorId;
    private BigDecimal internalCost;
    private Instant createdAt;

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getAuthorId() {
        return authorId;
    }

    public BigDecimal getInternalCost() {
        return internalCost;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

The schema only exposes **id**, **title**, and **author**. Having **internalCost** on the Java class does not make it automatically queryable by clients. GraphQL only permits fields declared in the schema.

Separating object types from entities helps to:

- Avoid accidentally exposing internal data or sensitive fields.
- Change the database or persistence model without breaking the API contract.
- Design fields tailored to client needs instead of depending entirely on table structure.
- Aggregate data from multiple services or sources.
- Create multiple public view types for the same domain object when business requirements call for it.

However, there is no need to create a new DTO for every field if the default property data fetcher already works well and there are no security boundaries or special transformations. Choose a model that is just clear enough for the schema and business logic.

## 9. How fields are resolved

When GraphQL executes an operation, each field is resolved to a value. The component supplying that value is called a **DataFetcher** in GraphQL Java; in a Spring application, controller methods typically act as resolvers mapped to data fetchers.

For nested fields, a resolver usually receives a source object—the object returned by the parent field. For example:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author: Author!
}
~~~

When a client queries **book.author.name**, the high-level flow is:

1. The **Query.book** resolver returns a Book.
2. GraphQL passes that Book as the source object to the **Book.author** field.
3. The **Book.author** data fetcher returns an Author.
4. GraphQL passes the Author as the source object to the **Author.name** field.
5. The final result is assembled according to the selection set.

~~~mermaid
flowchart TD
    Q[Query.book] --> B[Book source object]
    B --> A[Book.author resolver]
    A --> AU[Author source object]
    AU --> N[Author.name resolver]
    N --> R[GraphQL response]
~~~

### Default property data fetcher

Not every field requires a dedicated resolver method. GraphQL Java provides a default property data fetcher that can read values from the source object by field name. Depending on the source object type, it can read:

- A key in a **Map** matching the field name.
- A JavaBean-convention getter such as **getTitle()**.
- A boolean getter such as **isPublished()**.
- A supported property accessor for the data type in GraphQL Java.

For example, if a resolver returns a Java object with **getId()** and **getTitle()**, GraphQL can use those properties for the **id** and **title** fields without writing two separate resolvers.

The property data fetcher does not automatically call repositories or external services to look up relationships. If the **author** field is not an existing property on the source object or requires querying data, implement an explicit resolver.

### Explicit resolvers

Write a dedicated resolver when a field needs to:

- Call a service or repository.
- Combine data from multiple sources.
- Transform formats or apply business rules.
- Enforce authorization checks.
- Accept arguments for filtering, sorting, or pagination.
- Optimize data loading via batch loading.

## 10. Mapping object types with Spring for GraphQL

Spring for GraphQL provides annotations to map Java methods to schema fields. Example:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author: Author!
}

type Author {
  id: ID!
  name: String!
}
~~~

Controller:

~~~java
@Controller
public class BookController {

    private final BookService bookService;
    private final AuthorService authorService;

    public BookController(
            BookService bookService,
            AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }
}
~~~

In this example:

- **@QueryMapping** maps the **book** method to the **Query.book** field.
- **@Argument** extracts the **id** argument value from the operation.
- **@SchemaMapping** maps the **author** method to the **Book.author** field.
- The **Book book** parameter is the source object for the **author** field.

If the method name matches the field name and the source type name can be inferred from the source parameter, you can use the shorthand form:

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

When the Java method name or source class does not reflect the names in the SDL, use **typeName** and **field** to map explicitly. This is useful when a Java class has a different name from the public object type.

An object type is not required to have its own dedicated controller. Resolvers can be organized by business domain, as long as each mapping accurately identifies the GraphQL type and field it serves.

## 11. Loading object relationships and the N+1 problem

A nested schema is very convenient for clients, but it can cause many data-fetching calls if a child field resolver issues a separate query for each source object.

Example query:

~~~graphql
query {
  books {
    id
    title
    author {
      name
    }
  }
}
~~~

If the **Book.author** resolver queries the database once per book, then for 100 books the server could execute 1 query for the list plus 100 queries for the authors. This is the N+1 problem.

You can use **@BatchMapping** to group source objects into a single load:

~~~java
@Controller
public class BookRelationController {

    private final AuthorService authorService;

    public BookRelationController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        List<String> authorIds = books.stream()
                .map(Book::getAuthorId)
                .distinct()
                .toList();

        Map<String, Author> authors =
                authorService.findAllByIds(authorIds);

        Map<Book, Author> result = new HashMap<>();
        for (Book book : books) {
            Author author = authors.get(book.getAuthorId());
            if (author != null) {
                result.put(book, author);
            }
        }
        return result;
    }
}
~~~

This is an illustrative example of a batch resolver; the service must return a map indexed by author ID. In a real implementation, handle books without an author, duplicate IDs, result ordering, and missing values in accordance with the schema's nullability.

DataLoader is another mechanism for batching and caching data loads within the scope of a single GraphQL execution. It fits well when multiple branches of a selection set need the same kind of data. Choosing between **@BatchMapping** and DataLoader depends on how resolvers are organized, caching needs, and batch loader reusability.

Batch loading changes how data is fetched at runtime without changing the public object type. Clients still query **Book.author** against the same schema.

## 12. Nullability of object fields

A field returning an object type can be nullable or non-null. Example:

~~~graphql
type Book {
  author: Author
  publisher: Publisher!
}
~~~

**author** can return null—for instance, if a book has not been assigned an author. **publisher** must return a valid Publisher; if the resolver returns null, GraphQL produces an execution error and propagates null up to the nearest nullable parent field.

For object list fields:

| Declaration | Meaning |
|---|---|
| **[Author]** | List can be null; elements can be null |
| **[Author]!** | List cannot be null; elements can be null |
| **[Author!]** | List can be null; elements cannot be null |
| **[Author!]!** | Both the list and every element cannot be null |

Example:

~~~graphql
type Book {
  relatedBooks: [Book!]!
}
~~~

If an element in the list violates non-null, the entire list becomes null. Because the list field is also non-null, the error can propagate further up to the parent object. Therefore, choose nullability based on what the data can actually guarantee.

## 13. Security at the object and field levels

Declaring a field in the schema makes it requestable by clients. That does not mean every user is allowed to see its value. Access control must be enforced on the server.

Example:

~~~graphql
type Book {
  id: ID!
  title: String!
  internalNotes: String
}
~~~

If **internalNotes** is meant only for editors, the server must check permissions when resolving the field or in the service layer. Do not rely on the frontend UI to hide the field, because clients can craft and send operations directly.

With Spring Security, you can combine method security in the service or resolver. Illustrative example:

~~~java
@PreAuthorize("hasAuthority('BOOK_EDITOR')")
@SchemaMapping(typeName = "Book", field = "internalNotes")
public String internalNotes(Book book) {
    return bookService.getInternalNotes(book.getId());
}
~~~

For security annotations to take effect, the application must enable method security and configure proper authentication and authorization. Checking permissions in the service layer is often helpful when the same business logic is invoked from GraphQL, REST, or other internal flows.

Beyond authorization, consider:

- Should sensitive fields appear in the public schema at all?
- Is the user permitted to access the object based on tenant or owner?
- Could a resolver accidentally return an object belonging to another tenant?
- Does a batch resolver enforce permissions for each source object?
- Do error messages leak internal data or sensitive identifiers?

## 14. Evolving object types safely

Object types are part of the API contract. The following changes can affect clients:

| Change | Possible impact |
|---|---|
| Add nullable field | Usually compatible with existing operations |
| Add non-null field | Every resolver must guarantee a value; can cause runtime errors |
| Remove field | Operations selecting that field become invalid |
| Rename field | Equivalent to removing the old field and adding a new one |
| Change nullable to non-null | Changes data guarantees and can error if the source returns null |
| Change non-null to nullable | Clients must accept the possibility of receiving null |
| Add required argument | Existing operations may omit the argument and become invalid |
| Add argument with default | Usually less disruptive because existing clients can omit it |

Example when replacing an old field:

~~~graphql
type Book {
  id: ID!
  name: String @deprecated(reason: "Use title")
  title: String!
}
~~~

Keeping the old field for a transition window helps clients migrate gradually to **title**. Before removing a deprecated field, check its usage metrics and coordinate a client upgrade schedule.

Do not make a field non-null merely because current data usually has a value. Consider historical data, external sources, access permissions, and failure cases before making a new guarantee.

## 15. Testing object types and resolvers

Tests should verify both the public schema and how resolvers supply data. With Spring for GraphQL, **GraphQlTester** can execute operations and inspect paths in the response.

Example:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-01") {
                id
                title
                author {
                    name
                }
            }
        }
        """)
    .execute()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("GraphQL with Spring");
~~~

You can add checks for relational fields:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-01") {
                author {
                    name
                }
            }
        }
        """)
    .execute()
    .path("book.author.name")
    .entity(String.class)
    .isEqualTo("Ada Lovelace");
~~~

Scenarios that should be tested:

1. The object exists and basic fields return the expected values.
2. The object does not exist and the root field returns null according to the schema.
3. A relational field has no data and nullability is handled properly.
4. Arguments are passed, omitted, or receive default values correctly.
5. An unauthorized user cannot read a protected field.
6. Batch resolvers handle empty lists, duplicate IDs, and missing items.
7. Resolver failures produce GraphQL errors and null propagation matching the contract.
8. Operations with invalid selection sets are rejected during validation.

Service unit tests remain important because the GraphQL tester does not replace testing business logic. Keep tests focused on behavior observable by API consumers.

## 16. Common object type design mistakes

| Mistake | Why it is a problem | How to address it |
|---|---|---|
| Using an object type as an argument | Object types are output types | Create an input object |
| Exposing every entity field in the schema | Can leak internal data | Design object types around the public contract |
| Marking every field as non-null | Does not reflect missing-data cases | Choose nullability based on actual guarantees |
| Writing resolvers for every simple property | Adds unnecessary code and complexity | Use the property data fetcher when appropriate |
| Relation resolver queries separately per source | Easily causes N+1 queries | Use batch loading or DataLoader |
| Leaving pagination arguments unbounded | Clients can request overly large datasets | Validate and cap sizes |
| Recursive fields without query limits | Deep queries can consume excessive resources | Enforce depth/complexity limits |
| Checking permissions only in the frontend | Clients can call fields directly | Enforce authorization on the server |
| Renaming fields immediately | Breaks existing client operations | Add a new field, deprecate the old one, then remove on a schedule |

## 17. Object type design workflow

When designing a new object type for Spring for GraphQL, you can follow this sequence:

1. Identify which business concept this object represents and which clients need to read it.
2. Choose the public fields, field names, and corresponding output types.
3. Identify scalar, enum, object relation, interface/union, and list fields.
4. Choose nullability based on real data and what resolvers can guarantee.
5. Design arguments and dedicated input objects if fields need parameters.
6. Determine which fields use the default property data fetcher and which need explicit resolvers.
7. Check whether nested relationships introduce N+1 risks or overly deep queries.
8. Add server-side authorization for sensitive objects and fields.
9. Write sample operations and test them with GraphQlTester.
10. Evaluate backward compatibility before changing published fields or nullability.

Object types are the structure clients see when reading data from a GraphQL API. Good design lets clients query the exact slice of data they need while keeping the server free to organize its Java models, persistence, and data-loading strategies. In Spring for GraphQL, SDL defines the contract; the property data fetcher and resolvers such as **@SchemaMapping** supply values; and batch loading, security, and testing ensure objects are returned accurately, safely, and efficiently.
