# Clients Select the Exact Data They Need

A book listing screen typically only needs the book ID, title, and author name. A detail screen also needs the summary, publication year, topic tags, and full author details. If the API always returns all data for both screens, the client must receive and process many unused fields. If the API only returns a fixed structure per screen, the backend may end up creating many nearly identical endpoints.

GraphQL solves this problem with the **selection set**: in each operation, the client declares the exact fields it wants to receive. The server validates the request against the schema, executes the selected fields, and returns data with the corresponding shape. This approach is an important foundation when building APIs with Spring for GraphQL: the schema describes the queryable data, while resolvers provide values for the fields requested by the operation.

After this lesson, you will be able to read and write selection sets, select nested fields, pass arguments via variables, rename fields with aliases, reuse fragments, and understand how those selections are executed on the server.

## 1. Selection sets determine the shape of the returned data

A GraphQL operation consists of an operation name, arguments if needed, and a set of fields inside curly braces. This set of fields is called a selection set.

Consider a simple SDL schema for a book management application:

```graphql
type Query {
  book(id: ID!): Book
  books(limit: Int = 20, offset: Int = 0): [Book!]!
  searchBooks(keyword: String!, limit: Int = 10): [Book!]!
}

type Book {
  id: ID!
  title: String!
  summary: String
  publishedYear: Int
  tags: [String!]!
  author: Author!
}

type Author {
  id: ID!
  name: String!
  biography: String
}
```

The schema indicates that `Query` can provide a single book, a list of books, or search results. Each `Book` has fields such as `id`, `title`, `summary`, and `author`. `author` is an object of type `Author`, so the client can continue selecting fields inside the author.

For example, a screen that only needs the title and author name can send this query:

```graphql
query BookSummary {
  book(id: "book-42") {
    title
    author {
      name
    }
  }
}
```

The server returns a structure matching the selected fields:

```json
{
  "data": {
    "book": {
      "title": "Introduction to GraphQL",
      "author": {
        "name": "Nguyen An"
      }
    }
  }
}
```

The `id`, `summary`, `publishedYear`, and `tags` fields do not appear in the response because the query did not request them. Unselected fields are omitted from the returned object; this differs from a selected field whose value is `null`.

The selection set also applies to each element of a list. The following query asks the server to return a list of books, where each element only includes the ID, title, and author name:

```graphql
query BookList {
  books {
    id
    title
    author {
      name
    }
  }
}
```

The client does not need to declare a separate response type for lists and another for details. The same schema can serve multiple screens with different selection sets.

## 2. Selecting scalar fields and object fields

GraphQL distinguishes fields with scalar values from fields returning an object or a list of objects.

- **Scalars** such as `String`, `Int`, `Float`, `Boolean`, and `ID` are leaf values. Clients select scalar fields directly without placing a nested selection set inside.
- **Objects** such as `Book` or `Author` require a nested selection set to specify the fields to receive.
- **Lists of objects** also require a nested selection set for the object type of each element.

Valid query:

```graphql
query BookDetail {
  book(id: "book-42") {
    id
    title
    author {
      id
      name
      biography
    }
  }
}
```

The following examples are invalid:

```graphql
# Invalid: author is an object but has no nested selection set.
query {
  book(id: "book-42") {
    title
    author
  }
}

# Invalid: title is a scalar, so subfields cannot be selected.
query {
  book(id: "book-42") {
    title {
      length
    }
  }
}
```

GraphQL validates these type and structural errors before executing resolvers. Clients also cannot arbitrarily request a field not declared in the schema, such as `isbn` if the `Book` type has no such field. The schema is the shared contract between client and server covering field names, data types, arguments, and nullability.

## 3. Arguments select what to query; selection sets select what data to receive

Arguments and selection sets answer two different questions:

- **Arguments** determine the data or scope of data to query.
- **Selection sets** determine which fields to extract from that data.

For example, `limit` and `offset` select a slice of the book list; `id` identifies a specific book. The fields inside the curly braces define the contents of each result.

```graphql
query BookList {
  books(limit: 5, offset: 0) {
    id
    title
  }
}
```

When sending dynamic data, declare variables instead of embedding values directly into the query string:

```graphql
query SearchBooks($keyword: String!, $limit: Int = 10) {
  searchBooks(keyword: $keyword, limit: $limit) {
    id
    title
    author {
      name
    }
  }
}
```

The variables are sent separately in the payload:

```json
{
  "keyword": "GraphQL",
  "limit": 5
}
```

`String!` means the `keyword` variable is required to have a non-`null` value. `Int = 10` declares a default value for `limit` if the client omits this variable. The variable type must be compatible with the argument type declared by the schema.

Separating variables from the query lets you reuse the same operation across many input values, keeps queries readable, and avoids manually interpolating user input into the query string. When inspecting a request, look at both the document and the variables because together they determine the executed operation.

## 4. Using aliases when multiple results are needed from the same field

Aliases let clients specify a response key name different from the schema field name. Aliases are useful when an operation needs to call the same field multiple times with different arguments, or when you want clearer JSON key names.

Example of fetching two pages of books in the same request:

```graphql
query BookPages {
  firstPage: books(limit: 5, offset: 0) {
    id
    title
  }
  nextPage: books(limit: 5, offset: 5) {
    id
    title
  }
}
```

The response uses the aliases as keys:

```json
{
  "data": {
    "firstPage": [
      { "id": "book-1", "title": "Introduction to GraphQL" }
    ],
    "nextPage": [
      { "id": "book-6", "title": "API Design" }
    ]
  }
}
```

Aliases can also rename a single field:

```graphql
query BookTitle {
  book(id: "book-42") {
    displayTitle: title
  }
}
```

In the schema, the field is still `title`; in the response, the key will be `displayTitle`. Aliases only rename the field in the output; they do not create a new field on the server or change how resolvers are mapped.

If you call the same field multiple times with different arguments without an alias, GraphQL may report a conflict error because fields with the same name cannot produce a single unambiguous result key. Use aliases to distinguish those results.

## 5. Reusing selection sets with fragments

When multiple queries need the same basic information of a type, repeating fields makes documents verbose and hard to keep in sync. Fragments let you extract a shared group of fields into a named unit.

```graphql
fragment BookCardFields on Book {
  id
  title
  author {
    name
  }
}

query HomePage {
  books(limit: 8) {
    ...BookCardFields
  }
}

query SearchPage($keyword: String!) {
  searchBooks(keyword: $keyword, limit: 10) {
    ...BookCardFields
  }
}
```

`BookCardFields` applies to the `Book` type, so it can be used wherever the schema expects a `Book`. The `...BookCardFields` syntax spreads the fields from the fragment into the current selection set. When the server returns the result, fragments do not add an extra object layer; the fields are flattened directly into the corresponding object.

Fragments help screens share a consistent data structure. However, avoid cramming every possible field into one large fragment and reusing it on every screen. Doing so forces even small queries to request unnecessary data. Create fragments tailored to display needs, such as `BookCardFields` for list cards and `BookDetailFields` for detail pages.

## 6. Mutations and Subscriptions also select returned fields

Selection sets are not limited to Queries. Mutations and Subscriptions also return fields, so clients must still declare which fields they want to receive.

Example schema with a mutation to update a title:

```graphql
type Mutation {
  updateBookTitle(id: ID!, title: String!): Book!
}
```

The client can request the mutation to return the ID, the new title, and the author name:

```graphql
mutation UpdateBookTitle($id: ID!, $title: String!) {
  updateBookTitle(id: $id, title: $title) {
    id
    title
    author {
      name
    }
  }
}
```

Similarly, a subscription watching for book updates can select the data to receive in each event:

```graphql
subscription WatchBook($id: ID!) {
  bookUpdated(id: $id) {
    id
    title
  }
}
```

Selecting fields for the payload ensures the client receives the exact information it needs to process once a mutation finishes or when a new subscription event arrives.

## 7. How are selection sets executed in Spring for GraphQL?

In Spring for GraphQL, the SDL schema defines the queryable fields. Methods annotated with `@QueryMapping`, `@MutationMapping`, or `@SubscriptionMapping` typically handle the root fields of an operation. Nested fields can be handled with `@SchemaMapping`; if the source object already has a matching property, the default property access mechanism can supply the value without writing a separate resolver.

For example, the schema declares `book` and the `Book.author` field:

```graphql
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
```

A controller can supply the book and resolve the author as follows:

```java
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
        return authorService.findById(book.authorId());
    }
}
```

For a query that only selects `book { title }`, GraphQL needs the values of `book` and `title`. The `author` resolver does not need to be invoked because the client did not request that field. For a query that also selects `author { name }`, GraphQL proceeds to resolve `Book.author`, and then retrieves `Author.name`.

This is why selection sets can help the server avoid processing unrequested fields. However, it is important to understand the boundary: GraphQL does not automatically translate a selection set into a SQL query that fetches only those exact columns. If `bookService.findById` loads the full entity from the database, those columns are still read even if the response only includes `title`. To optimize database queries, the application needs to design appropriate projections, DTOs, repository queries, or data-loading strategies.

### Nested fields and the N+1 problem

Suppose a query fetches 20 books and selects `author { name }`. The simple `author` resolver above may be called once for each book. If each call triggers a separate database query, the server executes one query to fetch the list of books plus 20 additional queries to fetch authors. This is the N+1 problem.

Spring for GraphQL supports `@BatchMapping` to batch the resolution of a nested field across a group of source objects. The example below illustrates the idea: the service loads authors for a set of IDs, then maps each book to its corresponding author.

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    Map<String, Author> authorsById = authorService.findByIds(
            books.stream()
                    .map(Book::authorId)
                    .collect(Collectors.toSet())
    );

    return books.stream().collect(Collectors.toMap(
            Function.identity(),
            book -> authorsById.get(book.authorId())
    ));
}
```

The example assumes `findByIds` returns a `Map<String, Author>` keyed by author ID. In a real application, you should handle missing authors and ensure the map key type matches the source type. DataLoader also solves the problem of batching and caching data loads within the scope of a single GraphQL request.

The selection set indicates which fields need to be resolved; `@BatchMapping` or DataLoader makes resolving those fields efficient when there are many source objects. Therefore, selecting fewer fields can reduce payload size and the number of resolvers invoked, though you still need to monitor database queries and the actual cost of each field.

## 8. Testing queries and response shapes

When writing tests for a GraphQL API, send the exact document the client uses and verify the important fields in the response. `GraphQlTester` lets you execute documents, pass variables, and read results by path.

```java
graphQlTester.document("""
        query BookSummary($id: ID!) {
            book(id: $id) {
                id
                title
                author {
                    name
                }
            }
        }
        """)
    .variable("id", "book-42")
    .execute()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("Introduction to GraphQL");
```

You can also assert `book.author.name`, non-existent ID cases, nullable values, and errors thrown by resolvers. Include tests for both shallow selection sets and selection sets with nested fields to confirm resolvers work properly.

## 9. How to read responses: omitted fields, null fields, and errors

The following three cases have distinct meanings:

1. **Unselected field:** the key does not appear in the response object. For example, the query does not select `summary`, so the response has no `summary` key.
2. **Selected nullable field with no value:** the key appears with a value of `null`.
3. **Non-null field whose resolver returns null or throws an error:** GraphQL records an error and applies null propagation up to the nearest nullable parent field. As a result, a portion of the response data may become null even though other fields succeeded.

GraphQL can return both `data` and `errors` at the same time. Clients should inspect both when handling responses, especially for queries with many nested fields. Do not treat an omitted key in the response as missing data; first check the request's selection set.

## 10. Common issues when selecting data

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Cannot query field ...` | Field does not exist on the schema type or field name is misspelled | Check the schema, spelling, and parent object type |
| `Field ... must have a selection of subfields` | Selected an object field without declaring a nested selection set | Add the desired fields inside `{ ... }` |
| `Field ... must not have a selection since type ... has no subfields` | Placed a nested selection set on a scalar | Select the scalar field directly |
| Response is missing an expected key | Field was not selected or the response key was renamed with an alias | Check the selection set and aliases |
| Query returns too much data | Shared fragment includes many fields unnecessary for the current screen | Create purpose-specific fragments and select only needed fields |
| Query has a small payload yet is still slow | Resolver or database query for a selected field is expensive; possible N+1 | Measure resolver timings, optimize queries, and use batching/DataLoader when appropriate |

## 11. Principles for designing selection sets

- Start from the data the screen or task actually uses. For lists, usually only the ID, title, and a few summary fields are needed; detail pages need deeper data.
- Only expand the selection set across nested objects when the UI needs those fields. An object field does not have to fetch all of its subfields.
- Use variables for input data and aliases when multiple results of the same kind are needed in one operation.
- Use fragments for groups of fields genuinely shared across screens. Keep fragments small enough not to inadvertently inflate the data fetched by every query.
- Paginate large lists using arguments like `limit` and an appropriate cursor or offset. Do not request an unbounded list just because the client can select few fields.
- Evaluate server-side cost. A field might call an external service, query a database, or run an expensive computation even though the response only holds a single scalar value.
- Combine depth limits, query complexity limits, authentication, and field-level authorization where appropriate. Being able to select a field does not mean every field is authorized for access.

## 12. Practice exercise

Suppose a book card screen needs to display the title, publication year, and author name. Write a query fetching up to 10 books, using a variable for the limit and omitting `summary` and `biography`.

One possible solution is:

```graphql
query BookCards($limit: Int = 10) {
  books(limit: $limit) {
    id
    title
    publishedYear
    author {
      name
    }
  }
}
```

Next, extend the query to also fetch the author's biography when the user opens the detail page. Consider creating separate fragments for the book card and the detail page. Then write a test with `GraphQlTester` to assert that the `author.name` field is returned and verify that the `author` resolver is not invoked for a query that only fetches `id` and `title`.

When finished, keep in mind that the client describes the desired data via the selection set; the schema constrains which fields can be selected; and resolvers in Spring for GraphQL provide values for the requested fields. Well-designed selection sets keep responses compact and tailored to each screen, while actual performance also depends on how the server loads and processes data.
