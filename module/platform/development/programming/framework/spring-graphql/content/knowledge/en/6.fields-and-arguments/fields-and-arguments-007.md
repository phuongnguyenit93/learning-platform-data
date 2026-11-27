# Nested Field Selection

GraphQL allows clients to select nested fields to receive data shaped according to the object structure exposed by the API. Instead of calling multiple endpoints to fetch a book, its author, and its list of reviews, the client can describe all required data in a single operation. Describing fields inside other fields is called **nested field selection**.

In Spring for GraphQL, the GraphQL engine reads the selection set and resolves each field according to the schema. Spring connects those fields to properties on the returned object or to resolver methods such as `@SchemaMapping`. Understanding how selection sets work helps you design clear responses, place resolvers appropriately, and control nested queries that could otherwise trigger N+1 problems.

## 1. What is a selection set?

A selection set is the group of fields enclosed in curly braces of an operation or of a field returning an object.

Schema example:

~~~graphql
type Query {
    book(id: ID!): Book
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
~~~

The client can select both the book and its author in the same request:

~~~graphql
query BookDetail {
    book(id: "book-42") {
        id
        title
        author {
            id
            name
        }
    }
}
~~~

This structure has three levels:

1. Root field `book` on type `Query`.
2. Fields `id`, `title`, and `author` on type `Book`.
3. Fields `id` and `name` on type `Author`.

The selection set of `book` sits inside the `book` field; the selection set of `author` sits inside the `author` field. Each level must conform to its parent field's type.

The response has a matching structure:

~~~json
{
    "data": {
        "book": {
            "id": "book-42",
            "title": "Spring in Action",
            "author": {
                "id": "author-7",
                "name": "Lan"
            }
        }
    }
}
~~~

The client decides which fields appear in the response. If `author` is not selected, the server does not need to return the author object in that operation's result.

## 2. Field selection rules by data type

GraphQL distinguishes leaf types from composite types when validating a selection set.

| Return type | How to select |
| --- | --- |
| Scalars such as `String`, `Int`, `Boolean`, `ID` | Select directly, with no child selection set. |
| Enum | Select directly, with no child selection set. |
| Object | Must have a selection set specifying child fields. |
| Interface | Must have a selection set; inline fragments can be used for implementation-specific fields. |
| Union | Must have a selection set; inline fragments are typically used to fetch fields per concrete type. |
| List | Selection depends on the element type; object lists require a selection set for each object. |

Valid example:

~~~graphql
query {
    book(id: "book-42") {
        title
        author {
            name
        }
    }
}
~~~

Invalid example because `author` returns an object without a selection set:

~~~graphql
query {
    book(id: "book-42") {
        title
        author
    }
}
~~~

Invalid example because `title` is a scalar:

~~~graphql
query {
    book(id: "book-42") {
        title {
            length
        }
    }
}
~~~

This rule is checked before resolvers run. If the selection set does not match the types in the schema, GraphQL returns a validation error and does not execute the operation.

### Object lists are also nested selections

A field returning a list of objects requires a selection set just like a field returning a single object:

~~~graphql
type Book {
    id: ID!
    title: String!
    reviews: [Review!]!
}

type Review {
    id: ID!
    rating: Int!
    comment: String
}
~~~

The client selects fields on each element:

~~~graphql
query BookReviews {
    book(id: "book-42") {
        title
        reviews {
            id
            rating
            comment
        }
    }
}
~~~

Response:

~~~json
{
    "data": {
        "book": {
            "title": "Spring in Action",
            "reviews": [
                {
                    "id": "review-1",
                    "rating": 5,
                    "comment": "Very helpful"
                },
                {
                    "id": "review-2",
                    "rating": 4,
                    "comment": null
                }
            ]
        }
    }
}
~~~

The selection set describes the structure of each element in the list. If the list is empty, the response contains an empty array; if the field allows null, the result can also be null per the schema contract.

## 3. Selection sets can be nested to many levels

An operation can traverse multiple object relationships. For example, a library system has Book, Author, Publisher, and Address:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    author: Author
}

type Author {
    id: ID!
    name: String!
    publisher: Publisher
}

type Publisher {
    name: String!
    address: Address
}

type Address {
    city: String!
    country: String!
}
~~~

The client can select across multiple levels:

~~~graphql
query BookPublisher {
    book(id: "book-42") {
        title
        author {
            name
            publisher {
                name
                address {
                    city
                    country
                }
            }
        }
    }
}
~~~

The response mirrors the nested relationships:

~~~json
{
    "data": {
        "book": {
            "title": "Spring in Action",
            "author": {
                "name": "Lan",
                "publisher": {
                    "name": "Tech Books",
                    "address": {
                        "city": "Ho Chi Minh City",
                        "country": "Vietnam"
                    }
                }
            }
        }
    }
}
~~~

Being able to select deeply does not mean clients should query arbitrarily deep. A child field can trigger database queries, call remote services, or perform expensive calculations. When a schema has multi-level nested relationships, the server should control operation depth and cost.

## 4. Arguments on nested fields

Arguments do not appear only on root fields. Any field in the schema can declare arguments if business logic requires dedicated parameters.

Example:

~~~graphql
type Book {
    id: ID!
    title: String!
    reviews(first: Int = 10, minRating: Int): [Review!]!
}

type Review {
    id: ID!
    rating: Int!
    comment: String
}
~~~

The client can pass arguments directly to the nested field:

~~~graphql
query BookReviewPreview {
    book(id: "book-42") {
        title
        reviews(first: 3, minRating: 4) {
            rating
            comment
        }
    }
}
~~~

Here `first` and `minRating` belong to `Book.reviews`, not `Query.book`. This lets each relationship define its own filtering or limiting options.

In Spring for GraphQL, a nested field resolver receives the source object and the arguments:

~~~java
@Controller
public class BookReviewController {

    private final ReviewService reviewService;

    public BookReviewController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @SchemaMapping(typeName = "Book", field = "reviews")
    public List<Review> reviews(
            Book book,
            @Argument("first") Integer first,
            @Argument("minRating") Integer minRating) {
        return reviewService.findReviews(book.id(), first, minRating);
    }
}
~~~

The `Book book` parameter is the source object on which the `reviews` field is being resolved. `@Argument` retrieves the values passed by the client on this field itself.

Default values and limits should be clearly enforced in the business layer. For example, `first` has a default in SDL, yet a client could still pass a negative number or an excessively large number if the schema only declares type `Int`. The resolver should validate and enforce maximum limits.

## 5. How does Spring for GraphQL resolve nested fields?

GraphQL Java executes operations according to the schema. When a field returns an object, the engine continues resolving the fields the client selected on that object. Spring for GraphQL provides mapping methods so applications can handle fields requiring custom logic.

General flow:

~~~mermaid
flowchart TD
    A["Client sends selection set"] --> B["GraphQL validates against schema"]
    B --> C["Root resolver: Query.book"]
    C --> D["Returns Book"]
    D --> E["Reads selected fields on Book"]
    E --> F["Property access or @SchemaMapping"]
    F --> G["Returns Author / Review"]
    G --> H["Continues resolving child fields"]
    H --> I["Builds response matching selection set"]
~~~

Schema example:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    author: Author
}
~~~

Root resolver:

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
~~~

If the `Book` object already exposes `id` and `title` via getters or record accessors, GraphQL can retrieve those values using the default property data fetcher. Not every field needs its own resolver method.

When a field needs to query additional data or execute logic, use `@SchemaMapping`:

~~~java
@Controller
public class BookAuthorController {

    private final AuthorService authorService;

    public BookAuthorController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
~~~

This method maps the `author` field of the `Book` type. Spring passes the `Book` source object as the first parameter, and the method uses data from Book to look up the Author.

`typeName` or `field` can be omitted in some cases because Spring can infer them from the method name and source parameter type. However, specifying names explicitly makes mappings easier to read, especially when the schema has many types or Java method names differ from field names.

### When is @SchemaMapping needed?

Use property access when the value is already present on the source object and requires no extra logic. Use `@SchemaMapping` when you need to:

- Load a relationship from a repository or service.
- Transform or compute a field value.
- Pass nested field arguments down to a service.
- Apply business rules or custom error handling for the field.
- Integrate with DataLoader to batch-load data.

Do not create a resolver merely to re-read a simple property if property access already satisfies the schema contract. The number and complexity of resolvers should reflect actual required logic.

## 6. Fragments in nested selection

When multiple operations or branches need to select the same group of fields, you can use fragments to reuse the selection set.

~~~graphql
fragment AuthorSummary on Author {
    id
    name
}

query BookAndAuthor {
    book(id: "book-42") {
        id
        title
        author {
            ...AuthorSummary
        }
    }
}
~~~

The `AuthorSummary` fragment is defined on type `Author`. When used inside `author`, GraphQL verifies that the fragment matches the field's type.

Fragments can be nested:

~~~graphql
fragment PublisherDetails on Publisher {
    name
    address {
        city
        country
    }
}

fragment AuthorDetails on Author {
    id
    name
    publisher {
        ...PublisherDetails
    }
}

query BookDetails {
    book(id: "book-42") {
        title
        author {
            ...AuthorDetails
        }
    }
}
~~~

Fragments only reuse selection set structure. They do not create extra endpoints or separate resolvers; fields are still executed according to the existing schema and mappings.

### Inline fragments with interfaces and unions

If a field returns an interface or union, clients can use inline fragments to select specific fields based on the actual type.

~~~graphql
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

type Query {
    search(keyword: String!): [SearchResult!]!
}
~~~

Operation:

~~~graphql
query Search($keyword: String!) {
    search(keyword: $keyword) {
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

`__typename` is a meta field indicating the concrete type of the object. The inline fragment `... on Book` selects `title` only when the result is a Book; `... on Author` selects `name` when the result is an Author.

This pattern is useful when a result list contains multiple object types. Clients still receive a unified response while handling each type individually.

## 7. Multiple nested fields and the N+1 problem

Nested selection lets clients fetch related data in one operation. However, a single HTTP request does not mean the server executes only one database query.

Suppose a client fetches 50 books and selects their authors:

~~~graphql
query BooksWithAuthors {
    books {
        id
        title
        author {
            id
            name
        }
    }
}
~~~

If the `Book.author` resolver calls the repository once per book, the server may execute:

- One query to fetch the list of 50 books.
- 50 separate queries to fetch the 50 authors.

This is the N+1 problem. The number of data accesses grows with the number of parent items, slowing down requests on large lists.

You can solve this with DataLoader or `@BatchMapping`. Example:

~~~java
@Controller
public class BookAuthorController {

    private final AuthorService authorService;

    public BookAuthorController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        List<String> authorIds = books.stream()
                .map(Book::authorId)
                .distinct()
                .toList();

        Map<String, Author> authorsById =
                authorService.findAllByIds(authorIds);

        return books.stream()
                .filter(book -> authorsById.containsKey(book.authorId()))
                .collect(Collectors.toMap(
                        book -> book,
                        book -> authorsById.get(book.authorId())
                ));
    }
}
~~~

`@BatchMapping` collects all `Book` source objects needing their `author` field resolved into a single batch method call. The example extracts unique author IDs, loads authors in bulk, and returns a map associating each `Book` with its corresponding `Author`.

Make sure batch implementations properly handle cases such as:

- Multiple `Book` instances referencing the same `Author`.
- No matching `Author` found.
- Batch query results returning in a different order than the input keys.
- Some source objects having a null relationship or missing foreign key.

If using DataLoader directly, the batch loader must return results following the exact mapping rules required by DataLoader. Never assume database query results always arrive in the same order as the input key list.

### Measuring batching effectiveness

Check the number of repository or database calls before and after batching:

| Scenario | Per-Book resolver | Batch resolver |
| --- | --- | --- |
| Fetch 1 Book | One Author load | One batch Author load |
| Fetch 20 Books | Potentially 20 Author loads | One batch for the group of Books |
| Multiple Books with the same Author | May repeatedly load the same Author | Can deduplicate IDs before loading |

The exact call count also depends on pagination, DataLoader dispatch scope, and service implementation. Measure with logs, metrics, or test spies instead of relying on assumptions.

## 8. Nested selection does not mean always loading every relationship

Clients select only the fields they need. Resolvers should also perform only the work needed for the requested fields. If an operation only selects:

~~~graphql
query BookTitles {
    books {
        id
        title
    }
}
~~~

then GraphQL does not need to resolve `Book.author` or `Book.reviews`. Resolvers for those fields are not invoked merely because they exist in the schema.

This is a key advantage of GraphQL: clients specify the exact shape of data they want. However, if the root resolver always joins and eagerly loads every relationship before GraphQL knows the selection set, the application may still over-fetch data. Repository and database query design should consider actual operation needs.

For advanced optimization cases, GraphQL Java exposes selection set information via `DataFetchingFieldSelectionSet`. Resolvers or services can use that information to choose an appropriate query strategy, while being careful with aliases, fragments, and nested fields. Never turn the selection set into an authorization mechanism; authorization must be checked independently on the server.

## 9. Security and limiting nested selection

A client can request many object levels, invoke many nested fields, or repeat a field with different arguments. Production APIs therefore need sensible limits.

**Check permissions per field.** A user allowed to read a Book is not necessarily allowed to read all nested data, such as an Author's private details or a Publisher's internal data.

**Limit depth.** Prevent operations from traversing overly deep relationships or expensive relationship cycles.

**Limit complexity.** A list field can return many items; combining with nested lists causes the object count to grow rapidly. Restrict page sizes, query complexity, or per-field costs.

**Validate arguments on nested fields.** Parameters like `first`, `limit`, and `offset` must be validated and bounded on the server.

**Prevent resolvers from exposing sensitive data.** A selection set is a client request, not an access grant. The server must decide which fields the current user is permitted to view.

For example, if a `Book` has an `internalNotes` field, it should not be returned just because a client added that field name to the operation. Access rights must be enforced at the resolver or corresponding security layer.

## 10. Common mistakes when selecting nested fields

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Object field reports missing selection set | Client selected an object field without child fields. | Add a selection set matching the object type. |
| Scalar or enum reports selection set error | Client placed curly braces after a leaf field. | Select the scalar or enum directly. |
| Nested field returns null | Source object lacks data or resolver returned null. | Check the source object, property accessors, and mapping. |
| Nested resolver is not called | Field is not in the selection set or mapping mismatches type/field. | Check the operation and `@SchemaMapping` annotation. |
| Nested argument receives null | Argument placed on the wrong field or `@Argument` name mismatches schema. | Place the argument on the right field and check names. |
| Response shape differs from expectations | Aliases, fragments, or selection sets produced different keys/branches. | Compare operation and response level by level. |
| Querying multiple objects is slow | Child resolver accesses data separately per object. | Measure query count and apply DataLoader or `@BatchMapping`. |
| Nested field is rejected | Access permissions or depth/cost limits blocked the operation. | Check security policies and query limits. |

When debugging, start from the schema and operation document. Confirm each field has the right type and selection set, then inspect the root resolver, source object, and nested resolver. If the data is correct but response time grows with the number of objects, measure service/repository call counts to identify N+1 behavior.

## 11. Testing nested field selection

Use `GraphQlTester` to verify an operation with nested selections:

~~~java
@Test
void returnsBookWithAuthor() {
    graphQlTester.document("""
            query BookDetail($id: ID!) {
                book(id: $id) {
                    id
                    title
                    author {
                        id
                        name
                    }
                }
            }
            """)
        .variable("id", "book-42")
        .execute()
        .path("book.author.name")
        .entity(String.class)
        .isEqualTo("Lan");
}
~~~

Beyond checking returned values, verify:

- Nullable child fields properly return null when a relationship does not exist.
- Non-null fields handle errors according to null propagation rules.
- Nested fields receive the expected arguments and apply filtering/pagination.
- Fragments and aliases produce the expected response keys.
- Resolvers are not called when fields are absent from the selection set.
- Batch resolvers reduce repository calls when handling multiple parent objects.
- Unauthorized users cannot read sensitive fields.

To test for N+1 issues, use mocks or spies on repositories and assert call counts. For integration tests, use datasets with multiple parent objects and multiple child objects to measure actual query counts.

## 12. Key takeaways

- Nested field selection is how clients describe nested object data within a single operation.
- Objects, interfaces, unions, and object lists require appropriate selection sets; scalars and enums are leaf fields.
- Arguments can be declared on nested fields, not only on root Queries.
- Spring for GraphQL uses property access for existing properties and `@SchemaMapping` for custom field resolution logic.
- Fragments help reuse selection sets; inline fragments handle fields by concrete type for interfaces or unions.
- A single GraphQL request can cause multiple server-side data accesses; DataLoader and `@BatchMapping` solve N+1 problems.
- Selection sets do not replace authorization; the server must still check permissions and enforce operation cost limits.

Nested field selection gives clients the exact data structure they need in one GraphQL operation. When combined with a clear schema, focused resolvers, and proper batching, a Spring for GraphQL application can serve complex data relationships while preserving performance and control.
