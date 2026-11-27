# Fragments

## 1. What is a fragment in GraphQL?

When an application has multiple screens that need the same group of fields, GraphQL operations often repeat the same selection set. For example, a book list page, a search page, and a detail page all need `id`, `title`, and part of the author's information. If each query redeclares those fields on its own, query documents become long, hard to keep in sync, and prone to missing fields when the schema changes.

GraphQL provides **fragments** to name a reusable selection set. The client declares a fragment once and expands it in appropriate places using a fragment spread. Fragments help organize queries and reuse field selection structures; they do not add fields to the schema, do not replace resolvers, and are not standalone requests.

A named fragment has the basic syntax:

```graphql
fragment BookSummary on Book {
    id
    title
    publishedAt
}
```

Where:

- `fragment` begins a fragment definition.
- `BookSummary` is the fragment name chosen by the client.
- `on Book` is the type condition: the fragment applies only to the `Book` object type.
- The selection set inside `{ ... }` lists the fields to fetch.

When using the fragment in an operation, the client writes `...BookSummary` at a position that can accept the `Book` type:

```graphql
query BookCatalog {
    books {
        ...BookSummary
    }
}

fragment BookSummary on Book {
    id
    title
    publishedAt
}
```

GraphQL processes the fragment spread as part of the selection set at the site of use. The result is still a standard GraphQL operation, sent and executed through the GraphQL endpoint.

## 2. Fragments are part of an executable document

GraphQL uses SDL to define schemas and executable documents to describe operations the client wants to run. `type`, `interface`, `union`, `input`, and `enum` belong to the schema definition; `query`, `mutation`, `subscription`, fragments, and selection sets belong to the executable document.

Schema example:

```graphql
type Query {
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
    publishedAt: String
}
```

Example executable document using that schema:

```graphql
query BookCatalog {
    books {
        ...BookSummary
    }
}

fragment BookSummary on Book {
    id
    title
    publishedAt
}
```

Fragments are not declared in `schema.graphqls` as object types. They are sent alongside the operation inside the query payload. The server needs the corresponding schema and resolvers to execute the fields requested by the fragment.

## 3. Named fragments and fragment spreads

### Declaring and using named fragments

A named fragment is a fragment with a name that can be used in multiple places within the same executable document. For example, a screen needing a list of books along with author info:

```graphql
fragment AuthorSummary on Author {
    id
    name
}

fragment BookSummary on Book {
    id
    title
    author {
        ...AuthorSummary
    }
}

query BookCatalog {
    books {
        ...BookSummary
    }
}
```

`BookSummary` contains the fragment spread `...AuthorSummary` inside the `author` field. GraphQL checks the type condition at each position: `BookSummary` is used in a list of `Book`, while `AuthorSummary` is used inside a field of type `Author`.

A fragment can be spread multiple times if the type condition matches:

```graphql
fragment BookIdentity on Book {
    id
    title
}

query CompareBooks($firstId: ID!, $secondId: ID!) {
    first: book(id: $firstId) {
        ...BookIdentity
    }
    second: book(id: $secondId) {
        ...BookIdentity
    }
}
```

Here the fragment is reused across two fields of the same type `Book`. The aliases `first` and `second` give distinct names to the two results in the response; the fragment merely reuses the selection set.

### Fragment spreads can combine multiple fragments

A selection set can spread multiple fragments:

```graphql
fragment BookIdentity on Book {
    id
    title
}

fragment BookPublication on Book {
    publishedAt
    isbn
}

query Books {
    books {
        ...BookIdentity
        ...BookPublication
    }
}
```

The result for each element includes all fields from both fragments. If fields sharing the same response key have incompatible calls or types, GraphQL validation may report a field conflict error. Therefore, split fragments along meaningful field groups and avoid overlapping selection sets that are hard to manage.

## 4. Inline fragments

An inline fragment is a selection set written directly at the point of use without declaring a separate name. The common syntax is `... on TypeName { ... }`.

For example, a search result can be either a `Book` or an `Author`:

```graphql
union SearchResult = Book | Author

type Query {
    search(term: String!): [SearchResult!]!
}

type Book {
    id: ID!
    title: String!
}

type Author {
    id: ID!
    name: String!
}
```

The client uses inline fragments to select fields based on the actual object type:

```graphql
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
```

If an item is a `Book`, GraphQL executes the `... on Book` branch; if it is an `Author`, GraphQL executes the `... on Author` branch. `__typename` helps the client identify the concrete object type in the response.

Inline fragments are also useful with interfaces. The client can select shared fields directly on the interface, then select type-specific fields using type conditions:

```graphql
interface Searchable {
    id: ID!
}

type Book implements Searchable {
    id: ID!
    title: String!
}

type Author implements Searchable {
    id: ID!
    name: String!
}

type Query {
    searchableItems: [Searchable!]!
}
```

Operation:

```graphql
query SearchableItems {
    searchableItems {
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

`id` is selected directly because it belongs to the `Searchable` interface. The fields `title` and `name` are selected only inside fragments with the corresponding type conditions.

### Inline fragments without a type condition

GraphQL also allows inline fragments without `on TypeName`. This form groups fields and can attach directives without changing the type condition:

```graphql
query BookDetails {
    book(id: "book-42") {
        id
        ... {
            title
            publishedAt
        }
    }
}
```

An inline fragment without a type condition preserves the type of its enclosing context. The form with a type condition is usually clearer when working with interfaces or unions.

## 5. Fragments on objects, interfaces, and unions

The type condition determines where a fragment can be used. GraphQL accepts a fragment only when the type at the site of use is potentially compatible with the type condition.

| Type condition | Usage |
| --- | --- |
| Object type, e.g. `Book` | Select fields belonging to `Book` |
| Interface, e.g. `Node` | Select common fields exposed by the interface for matching implementing objects |
| Union, e.g. `SearchResult` | Select fields per member object type using nested fragments inside |

Example fragment on a union:

```graphql
union SearchResult = Book | Author | Publisher

fragment SearchResultCard on SearchResult {
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

query Search($term: String!) {
    search(term: $term) {
        ...SearchResultCard
    }
}
```

The `SearchResultCard` fragment has the union `SearchResult` as its type condition. Inside the fragment, inline fragments specify concrete fields for each member object type. Because unions have no shared business fields, `__typename` is the meta-field used to identify the runtime type.

Example of an invalid type condition:

```graphql
query Search {
    search {
        ... on Order {
            id
            total
        }
    }
}
```

If `Order` is not a member of the `SearchResult` union and cannot appear at this position, GraphQL validation rejects the fragment because the types cannot intersect. Choose a type condition that has a valid relationship with the type where the fragment is spread.

## 6. Using fragments with variables and arguments

Fragments do not have their own parameter lists like fields or functions. If a fragment needs dynamic values, it can reference variables declared in the operation that uses the fragment. Variables remain scoped to the operation and are not declared inside the fragment.

Example:

```graphql
fragment BookDetails on Book {
    id
    title
    author {
        id
        name
    }
}

query BookCatalog($first: Int!, $authorId: ID) {
    books(first: $first, authorId: $authorId) {
        ...BookDetails
    }
}
```

Illustrative schema:

```graphql
type Query {
    books(first: Int!, authorId: ID): [Book!]!
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
```

JSON request:

```json
{
  "query": "fragment BookDetails on Book { id title author { id name } } query BookCatalog($first: Int!, $authorId: ID) { books(first: $first, authorId: $authorId) { ...BookDetails } }",
  "operationName": "BookCatalog",
  "variables": {
    "first": 20,
    "authorId": "author-7"
  }
}
```

When a fragment uses a variable in a field argument or directive, the operation using that fragment must declare that variable with a compatible type. If the variable is undeclared or declared with an incompatible type, GraphQL validation reports an error before executing resolvers.

## 7. Combining fragments with directives

Directives allow conditionally including a field or fragment in the result. Two standard commonly used directives are `@include(if: Boolean!)` and `@skip(if: Boolean!)`.

Example toggling a details section:

```graphql
fragment BookDetails on Book {
    isbn
    publishedAt
}

query BookCatalog($showDetails: Boolean!) {
    books {
        id
        title
        ...BookDetails @include(if: $showDetails)
    }
}
```

When `showDetails` is `true`, the fields inside the fragment are included in the result; when `false`, the fragment spread is omitted. With `@skip`, the inverse logic applies.

Directives can also be placed on inline fragments:

```graphql
query BookDetails($showPublication: Boolean!) {
    book(id: "book-42") {
        id
        title
        ... on Book @include(if: $showPublication) {
            publishedAt
            isbn
        }
    }
}
```

Standard directives affect only the selection set in the operation. They are not an authorization mechanism; the server must still enforce access checks in resolvers or the business layer for all requested fields.

## 8. Validation rules and limitations of fragments

Fragments must obey the executable document validation rules:

1. Fragment names must be unique within the document and cannot be named `on`.
2. The type condition must reference a valid type; the fragment must be applicable at the spread position.
3. A fragment spread must reference a fragment defined in the same document.
4. Fragments must not form reference cycles. For example, A spreading B and B spreading A is invalid.
5. Fragments must be used; unreferenced fragments are typically rejected by validation under the unused-fragments rule.
6. Every variable referenced in a fragment must be declared in the operation using the fragment with a compatible type.
7. Fields after combining fragments must still satisfy GraphQL rules for field selection, arguments, aliases, and types.

Invalid cycle example:

```graphql
fragment BookPart on Book {
    id
    ...AuthorPart
}

fragment AuthorPart on Book {
    title
    ...BookPart
}
```

This example creates a loop between two fragments. GraphQL cannot expand an infinite selection set, so the document is rejected.

Fragments are also not functions with parameters. You cannot declare `fragment BookCard($showAuthor: Boolean!)`. Use variables on the operation and directives on fragment spreads or fields if you need conditional selection.

## 9. How are fragments executed on the server?

Fragments are a way to organize executable documents on the client side. When the server receives a request, the GraphQL engine parses the document, validates the operation, expands fragment spreads for execution, and builds an execution plan for the selected fields. Using fragments does not create a new resolver and does not require a separate endpoint.

With Spring for GraphQL, controllers still map schema fields using `@QueryMapping`, `@MutationMapping`, or `@SchemaMapping`. Resolvers do not need to know whether a field was requested directly or through a fragment.

Schema example:

```graphql
type Query {
    books: [Book!]!
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
```

Illustrative controller:

```java
import java.util.List;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }
}
```

The client can query the `books` field directly or spread the `BookSummary` fragment at that field. In both cases, Spring for GraphQL resolves the same schema field and invokes the same data fetcher. If the selection set requests `author`, that field continues to be resolved by its corresponding mapping mechanism, such as `@SchemaMapping` or property access.

### Testing operations with fragments using GraphQlTester

`GraphQlTester` can send a document containing both an operation and fragments:

```java
graphQlTester.document("""
    query BookCatalog {
        books {
            ...BookSummary
        }
    }

    fragment BookSummary on Book {
        id
        title
    }
    """)
    .execute()
    .path("books[0].title")
    .entity(String.class)
    .isEqualTo("GraphQL in Practice");
```

This tests the operation at the GraphQL level. In a real test suite, also verify nested fragments, nullable fields, incompatible fragments, and variables used inside fragments.

## 10. Fragments, performance, and maintainability

Fragments reduce repetition in query source, but fragments themselves do not reduce the number of fields the server must resolve. If a fragment contains many fields and is spread into an operation, all selected fields remain part of the execution request.

Usage principles:

- Create fragments around display purposes or meaningful field groups, such as `BookCard`, `BookDetails`, or `AuthorSummary`.
- Keep fragments small enough that clients clearly see what data they request.
- Use nested fragments with restraint; avoid overly deep fragment chains that make the final selection set hard to trace.
- Do not bundle every field of an object into one large fragment if a screen only needs a small subset.
- Reuse fragments across operations that share the same data needs and type conditions.
- When changing the schema, check fragments using renamed or deprecated fields.

The GraphQL server still needs to measure query cost, limit depth/complexity when appropriate, and handle N+1 in resolvers. Splitting a query into fragments does not lower execution complexity; on the contrary, a large fragment can cause an operation to request more data than expected.

Fragments can also help clients cache data more consistently when multiple screens share the same field structure. However, normalized entity caching is a feature of client libraries; the GraphQL specification does not define a standard client cache.

## 11. Common errors when using fragments

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `Unknown fragment` | Fragment spread references an undefined name or the fragment is missing from the submitted document | Send the fragment definition with the operation and check spelling |
| Field not allowed to be selected | Fragment has an incompatible type condition or the field does not exist on that type | Check the schema and use the right type condition |
| Unused fragment | Fragment is defined but no fragment spread references it | Remove the unused fragment or add a spread to the operation |
| Fragment cycle | Fragments reference each other in a cycle | Reorganize fragments into an acyclic graph |
| Variable not defined | Fragment uses a variable not declared by the operation containing the spread | Declare the variable on the operation and pass it in `variables` |
| Field conflict | Fragments produce the same response key with incompatible arguments or types | Check aliases, arguments, and field structures after merging |
| Query remains slow despite using fragments | Fragments only reuse selection sets; they do not optimize resolvers or database calls | Profile resolvers, address N+1, and optimize backend queries |
| Response missing fields | `@include` or `@skip` directives excluded fields based on variables | Check variable values and directive conditions |

## 12. Fragment design checklist

- [ ] Does the fragment have a clear name reflecting the reused data group?
- [ ] Does the type condition match the type at the spread position?
- [ ] Are union- or interface-specific fields placed inside appropriate fragments?
- [ ] Does the operation sent to the server include all fragment definitions?
- [ ] Are variables used inside the fragment declared on the operation using it?
- [ ] Are there no cyclic fragment spreads or unused fragments?
- [ ] Are directives used in the right places and not mistaken for authorization?
- [ ] Does the fragment avoid bundling too many fields and causing overfetching?
- [ ] Are schema changes reviewed against existing fragments?
- [ ] Are operations with fragments tested using GraphQlTester or an equivalent tool?

## Conclusion

Fragments are the mechanism for reusing selection sets in GraphQL executable documents. Named fragments let you reuse a field group with an explicit type condition; inline fragments let you select fields by concrete object type, especially when working with interfaces and unions. Clients can combine fragments with variables and directives to organize operations flexibly.

In Spring for GraphQL, fragments are processed as part of the GraphQL document. Resolvers remain mapped to schema fields via `@QueryMapping`, `@MutationMapping`, or `@SchemaMapping`; no separate resolver is needed for a fragment. Using fragments intentionally keeps queries readable and maintainable, while you still manage selection sets, resolver costs, authorization, and testing like any other GraphQL operation.
