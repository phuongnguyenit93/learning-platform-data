# Object type

In the SPRING_GRAPHQL module, learners build GraphQL APIs with Spring for GraphQL by defining an SDL schema, implementing resolvers, and connecting fields to services. **Object types** are the central building blocks of a schema: they describe an object clients can query, consisting of a type name and a set of strongly typed fields.

For example, a book management system might publish the `Book`, `Author`, and `Review` object types. A book has an ID, title, author, and list of reviews. Through linked fields, clients can query a book together with related data in a single operation. Object types describe the API's data shape; they do not have to match entities, database tables, or internal application structures.

## Declaring an object type in SDL

In GraphQL Schema Definition Language (SDL), the **type** keyword declares an object type. Inside the curly braces is the list of fields:

~~~graphql
type Book {
  id: ID!
  title: String!
  subtitle: String
  author: Author!
  reviews(first: Int = 10): [Review!]!
}

type Author {
  id: ID!
  name: String!
  books: [Book!]!
}

type Review {
  id: ID!
  rating: Int!
  comment: String
}
~~~

The declarations above create three object types:

- **Book** describes a book. The `id` and `title` fields are required to have values; `subtitle` may be null.
- **Author** describes an author. The `books` field links to the author's list of books.
- **Review** describes a review. `rating` is a required integer, while `comment` is optional content.

Each object type must have at least one field. Type names are typically written in PascalCase such as `Book` or `Author`; field names are typically written in camelCase such as `publishedAt` or `authorId`. This is a common naming convention that keeps schemas consistent and readable.

A field is the unit of data a client can choose in a selection set. Each field has a name and a return type; a field can also accept arguments for filtering, pagination, or controlling how data is retrieved. In the example, `reviews` accepts a `first` argument and defaults to 10 when the client omits it.

## Object types are output types

Object types belong to the output type category. They can appear as the return type of a field in `Query`, `Mutation`, `Subscription`, or a nested field. A field's return type can be a scalar, enum, object, interface, or union; these types can also be wrapped with list and non-null modifiers.

Example:

~~~graphql
type Query {
  book(id: ID!): Book
  books(authorId: ID): [Book!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}

type Book {
  id: ID!
  title: String!
  author: Author
}

type Author {
  id: ID!
  name: String!
}

input CreateBookInput {
  title: String!
  authorId: ID!
}
~~~

In this schema, `Query` and `Mutation` are themselves object types. GraphQL requires a schema to have a `Query` root operation type; `Mutation` and `Subscription` root types are declared when the API needs write operations or event streams. The `book` field returns a `Book` that may not exist, so `Book` has no `!`. The `createBook` field returns `Book!` because the contract specifies the result cannot be null.

Object types are not used as input types for arguments. When you need to receive a group of values from the client, declare an **input object type** with the `input` keyword, like `CreateBookInput` above. An input object can only contain valid input types such as scalars, enums, or other input objects, optionally combined with list and non-null wrappers; it cannot contain fields of type `Book` or `Author`. This rule separates the data structure clients send from the data structure the server returns.

## Fields can hold scalars or other objects

An object type commonly combines several kinds of fields:

| Field kind | Example | Meaning |
| --- | --- | --- |
| Scalar | id: ID!, title: String! | Single value such as a string, number, or boolean |
| Enum | status: BookStatus! | One value from a predefined set of choices |
| Object | author: Author | Another object nested inside the current object |
| List | reviews: [Review!]! | A list of objects or values |
| Field with arguments | reviews(first: Int = 10): [Review!]! | A field accepting parameters to control returned data |

Enum example:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Book {
  id: ID!
  title: String!
  status: BookStatus!
}
~~~

An enum constrains valid values to the declared list. When an object type uses an enum, clients know in advance what states they can receive and can use them in appropriate variables or arguments.

Object-typed fields create relationships between types. For example, `Book.author` returns `Author`, while `Author.books` returns a list of `Book`. These relationships let clients navigate from one object to related objects according to the schema. A relationship can be one-to-one, one-to-many, or many-to-many depending on the domain model; SDL expresses the shape and cardinality of results, while resolvers are responsible for loading the actual data.

## Lists and non-null in object fields

GraphQL uses square brackets to represent lists and exclamation marks to represent non-null values. These two symbols can be combined, so you must read their positions carefully:

| Type | Can the list be null? | Can elements be null? |
| --- | --- | --- |
| [Book] | Yes | Yes |
| [Book!] | Yes | No |
| [Book]! | No | Yes |
| [Book!]! | No | No |

Example:

~~~graphql
type Author {
  biography: String
  books: [Book!]!
}
~~~

`biography` may have no content. Conversely, `books` must always return a list; an empty list is valid, but the list itself cannot be null and cannot contain null elements.

Nullability is part of the API contract and affects how GraphQL handles errors. If a nullable field's resolver returns null, the client receives null for that field. If a non-null field's resolver returns null or encounters an error preventing value resolution, GraphQL records an error and bubbles null up to the nearest nullable parent field. This process is called null propagation. If multiple parent levels are also non-null, null keeps bubbling up until a nullable position is reached; thus a deep non-null field can turn a larger portion of the response into null.

When choosing `!`, rely on business rules and real data guarantees. Mark a field non-null only when the application can guarantee a value in every valid scenario. If an author might be deleted or unknown, `author` should be declared nullable or the application must guarantee a valid fallback value.

## Querying nested objects

Clients do not receive all fields of an object by default. Clients send a selection set choosing only the fields they need. If a field returns another object, the client opens a nested selection set specifying which fields to read from that object.

~~~graphql
query FindBook($id: ID!) {
  book(id: $id) {
    id
    title
    author {
      id
      name
      books {
        id
        title
      }
    }
    reviews(first: 3) {
      id
      rating
      comment
    }
  }
}
~~~

This operation requests a book, its author information, the author's list of books, and the first three reviews. The response matches the selection set structure:

~~~json
{
  "data": {
    "book": {
      "id": "book-101",
      "title": "Spring in Action",
      "author": {
        "id": "author-12",
        "name": "Craig Walls",
        "books": [
          {
            "id": "book-101",
            "title": "Spring in Action"
          }
        ]
      },
      "reviews": [
        {
          "id": "review-1",
          "rating": 5,
          "comment": "Useful examples"
        }
      ]
    }
  }
}
~~~

A schema can describe cyclic relationships such as `Book.author` and `Author.books` referencing each other. This does not cause an infinite loop in the response, because the client must explicitly specify the selection set per operation and every operation has finite depth. The server should still enforce query depth or complexity limits to prevent overly large operations.

## Arguments on object fields

Arguments belong to individual fields, not to the entire object type. They allow clients to pass filters, sorting, pagination, or business options:

~~~graphql
type Book {
  id: ID!
  title: String!
  reviews(first: Int = 10, minRating: Int): [Review!]!
}
~~~

Clients can invoke the `reviews` field with different values:

~~~graphql
query {
  book(id: "book-101") {
    title
    recentReviews: reviews(first: 5, minRating: 4) {
      id
      rating
    }
  }
}
~~~

The alias `recentReviews` gives the field a different name in the response. The `first` argument requests up to five results, while `minRating` filters by rating score. The default value of `first` is used when the client omits the argument; if the client passes an explicit `null`, behavior depends on nullability and how the resolver handles it.

For large lists, design explicit pagination rather than letting clients load unbounded results. You can use limit/offset or cursor-based pagination depending on data consistency requirements and data-source access patterns. The schema should clearly document argument semantics and server-enforced maximum limits.

## Mapping object fields to Java in Spring for GraphQL

SDL describes the contract, while resolvers supply values for fields. Spring for GraphQL supports declaring resolvers with annotations on `@Controller` beans. Root fields under `Query` can use `@QueryMapping`; fields on object types can use `@SchemaMapping`.

Schema example:

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

Java models and controller:

~~~java
public record Book(String id, String title, String authorId) {
}

public record Author(String id, String name) {
}
~~~

~~~java
@Controller
public class BookGraphQlController {

    private final BookService bookService;
    private final AuthorService authorService;

    public BookGraphQlController(
            BookService bookService,
            AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    public Mono<Book> book(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Mono<Author> author(Book book) {
        return authorService.findById(book.authorId());
    }
}
~~~

The `book` method maps the `book` field on the root `Query` type. The `author` method maps the `author` field on the `Book` object type. The `Book book` parameter is the source object: it holds the result returned by the parent resolver. Spring for GraphQL passes this source object to the child field resolver, which then reads `authorId` and calls the service to fetch the author.

If the Java object already has properties matching the schema field names, GraphQL can use default property access to retrieve values without writing separate resolvers. For instance, the `Book` record has `id()` and `title()` accessors, so the `id` and `title` fields can be read directly. When a field needs to call a service, apply business rules, or fetch data from another source, write an explicit resolver with `@SchemaMapping`.

Object fields can also accept arguments. For example, `reviews(first: Int)` can map to:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
public Flux<Review> reviews(Book book, @Argument Integer first) {
    return reviewService.findByBookId(book.id(), first);
}
~~~

The `Book` parameter is the source object; the `first` parameter receives the field argument. Separating the source object and arguments lets the resolver access both the parent object being resolved and the options sent by the client.

## Object types and the N+1 problem

Nested object fields are convenient for clients, but they can trigger excessive data accesses if each child resolver independently calls a database or service. For example, a query fetching 100 books and selecting `author` could invoke the `author` resolver 100 times. This is the N+1 problem.

Spring for GraphQL supports `@BatchMapping` and `DataLoader` to batch data loading. Instead of querying the author for each book individually, a batch resolver receives a group of `Book` instances and loads authors for the list of `authorId` values. The repository or service layer must provide an actual batch-loading operation; merely collecting calls into one method that still queries the database one by one inside does not solve N+1.

In addition to batching, paginate lists, limit operation depth and complexity, set timeouts, and monitor execution time per resolver. An object type can link to many other objects, but a well-designed schema reflects business needs and enforces reasonable operational limits.

## Combining object types with interfaces and unions

Object types can implement an interface to share a common set of fields:

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

`Book` and `Author` are concrete object types. Both provide the `id` field per the `Node` contract while adding their own fields. Interfaces are useful when multiple object types share a common group of fields.

A union represents a value that can belong to one of several object types without requiring them to share fields:

~~~graphql
union SearchResult = Book | Author

type Query {
  search(text: String!): [SearchResult!]!
}
~~~

When clients query fields of a specific member type in a union, they use inline fragments:

~~~graphql
query Search {
  search(text: "Spring") {
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

Interfaces and unions expand how objects can be modeled in a schema. When using them, resolvers must return the right concrete object types so GraphQL can determine which fields apply.

## Object type design principles

When designing object types for a GraphQL API, start from the data and behaviors clients need, then choose appropriate fields and relationships:

1. **Name types after domain concepts.** `Book`, `Author`, or `Order` are clearer than names reflecting table or persistence class details.
2. **Expose fields intentionally.** Do not expose passwords, tokens, internal flags, or sensitive data in the schema simply because they exist on a Java entity.
3. **Choose nullability based on actual data.** Use `!` when the application can guarantee a value; weigh the impact of null propagation when fields fail.
4. **Design paginated lists.** Avoid fields that return unbounded numbers of records.
5. **Use input objects for incoming data.** Do not reuse output objects as inputs; the two structures have different purposes and rules.
6. **Monitor the cost of nested relationships.** Use batch loading when many objects require the same kind of related data.
7. **Keep the schema stable and evolvable.** When deprecating a field, mark it deprecated and give clients transition time before removing it.

Object types are how GraphQL describes the entities and relationships an API exposes. When fields, arguments, lists, and nullability are combined properly, the schema becomes a clear contract for clients. In Spring for GraphQL, `@QueryMapping` and `@SchemaMapping` connect that contract to Java resolvers; services and repositories handle data retrieval, while `DataLoader` or `@BatchMapping` keeps costs under control when objects have rich relationships.
