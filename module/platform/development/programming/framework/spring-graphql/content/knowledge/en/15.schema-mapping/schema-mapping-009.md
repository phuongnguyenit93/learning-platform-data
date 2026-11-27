# Mapping fields with arguments

In GraphQL, arguments can be declared on any field, not just root Query or Mutation fields. This allows clients to pass filtering, pagination, sorting, or display options directly on the nested field where they want to fetch data.

In Spring for GraphQL, a nested field with arguments is typically handled using **@SchemaMapping**. The resolver method receives the source object from the parent field and the argument values via **@Argument**. Understanding both kinds of data helps implement resolvers properly, avoid confusing parent field arguments with child field arguments, and keep performance under control when a field is invoked for many objects.

## 1. Arguments can appear on nested fields

Consider the schema of a book management system:

~~~graphql
type Query {
    books: [Book!]!
}

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

The `books` field belongs to the `Query` root type and takes no arguments. The `reviews` field belongs to the `Book` type and accepts two arguments:

- `first` limits the number of reviews to retrieve, defaulting to 10.
- `minRating` filters reviews by minimum rating.

The client can select the nested field and pass arguments directly there:

~~~graphql
query BookReviews {
    books {
        id
        title
        reviews(first: 3, minRating: 4) {
            id
            rating
            comment
        }
    }
}
~~~

In this operation, `first` and `minRating` belong to the `Book.reviews` field. They are not arguments of `Query.books`.

This is an important GraphQL characteristic: each field can declare its own set of arguments. Clients pass parameters only to the specific field they want to control, even when that field sits deep in the selection set.

## 2. Distinguishing parent field arguments from child field arguments

An operation can have arguments at multiple levels:

~~~graphql
type Query {
    books(authorId: ID!): [Book!]!
}

type Book {
    reviews(first: Int = 10, minRating: Int): [Review!]!
}
~~~

Client:

~~~graphql
query AuthorBooks($authorId: ID!, $first: Int!, $minRating: Int) {
    books(authorId: $authorId) {
        id
        title
        reviews(first: $first, minRating: $minRating) {
            id
            rating
        }
    }
}
~~~

There are two independent groups of arguments:

| Field | Argument | Purpose |
| --- | --- | --- |
| `Query.books` | `authorId` | Selects the list of books by a given author. |
| `Book.reviews` | `first` | Limits the number of reviews per book. |
| `Book.reviews` | `minRating` | Filters each book's reviews by rating. |

When Spring invokes the resolver for `Book.reviews`, the method receives this field's `first` and `minRating` arguments. The `authorId` argument was already used in the `Query.books` resolver; it does not automatically appear in the `Book.reviews` resolver.

If a child field resolver needs information from the parent object, read it from the source object. If it needs another parameter sent directly by the client to the child field, declare that argument in the SDL and receive it with `@Argument`.

## 3. Source object in `@SchemaMapping`

For a nested field, Spring for GraphQL provides the parent object as the source object for the resolver.

Example Java records:

~~~java
public record Book(
        String id,
        String title,
        String authorId
) {
}

public record Review(
        String id,
        int rating,
        String comment
) {
}
~~~

SDL:

~~~graphql
type Book {
    id: ID!
    title: String!
    reviews(first: Int = 10, minRating: Int): [Review!]!
}
~~~

Resolver:

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

        return reviewService.findByBook(
                book.id(),
                first,
                minRating
        );
    }
}
~~~

In the method above:

- `Book book` is the source object, i.e., the parent object currently being resolved by GraphQL.
- `@Argument("first")` reads the `first` argument of the `reviews` field.
- `@Argument("minRating")` reads the `minRating` argument of the `reviews` field.
- `ReviewService` queries data by the `Book` ID and filter conditions.

The source object is not data sent by the client as an argument. It is the result already returned by the parent-level resolver. Meanwhile, parameters annotated with `@Argument` are bound from the current operation.

### How does Spring determine the mapped field?

With the declaration:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(Book book, @Argument("first") Integer first) {
    return reviewService.findByBook(book.id(), first);
}
~~~

Spring maps the method to the `Book.reviews` field.

You can omit some attributes if Spring can infer them from the method name and source parameter type:

~~~java
@SchemaMapping
public List<Review> reviews(Book book, @Argument("first") Integer first) {
    return reviewService.findByBook(book.id(), first);
}
~~~

In this case, the source type name is inferred from `Book` and the field name from the `reviews` method. When the schema is large or the method name differs from the field name, writing `typeName` and `field` explicitly keeps the mapping readable and prevents confusion.

## 4. Receiving scalars, enums, and multiple arguments

Field arguments can be scalars, enums, or other valid input types.

Example schema:

~~~graphql
enum ReviewSort {
    NEWEST
    OLDEST
    HIGHEST_RATING
}

type Book {
    id: ID!
    reviews(
        first: Int = 10
        minRating: Int
        sort: ReviewSort = NEWEST
    ): [Review!]!
}
~~~

Resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(
        Book book,
        @Argument("first") Integer first,
        @Argument("minRating") Integer minRating,
        @Argument("sort") ReviewSort sort) {

    return reviewService.findReviews(
            book.id(),
            first,
            minRating,
            sort
    );
}
~~~

Java enum:

~~~java
public enum ReviewSort {
    NEWEST,
    OLDEST,
    HIGHEST_RATING
}
~~~

Client operation:

~~~graphql
query {
    books {
        id
        reviews(
            first: 5
            minRating: 4
            sort: HIGHEST_RATING
        ) {
            id
            rating
        }
    }
}
~~~

Enum literal names in a GraphQL document are not wrapped in quotes. When passed through JSON variables, enum values are represented as strings:

~~~json
{
    "sort": "HIGHEST_RATING"
}
~~~

In an actual operation, the variable must be declared with the matching enum type. GraphQL validates enum values before calling the resolver. If a client sends a value that does not exist in the schema, the request is rejected.

## 5. Using an input object as a nested field argument

When a field has many filter conditions, you can group them into an input object.

SDL:

~~~graphql
enum ReviewSort {
    NEWEST
    OLDEST
    HIGHEST_RATING
}

input ReviewFilterInput {
    minRating: Int
    verifiedOnly: Boolean
    sort: ReviewSort
}

type Book {
    id: ID!
    reviews(first: Int = 10, filter: ReviewFilterInput): [Review!]!
}
~~~

Java record:

~~~java
public record ReviewFilterInput(
        Integer minRating,
        Boolean verifiedOnly,
        ReviewSort sort
) {
}
~~~

Resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(
        Book book,
        @Argument("first") Integer first,
        @Argument("filter") ReviewFilterInput filter) {

    return reviewService.findReviews(book.id(), first, filter);
}
~~~

Client:

~~~graphql
query BookReviews($filter: ReviewFilterInput) {
    books {
        id
        reviews(first: 5, filter: $filter) {
            id
            rating
            comment
        }
    }
}
~~~

Variables:

~~~json
{
    "filter": {
        "minRating": 4,
        "verifiedOnly": true,
        "sort": "HIGHEST_RATING"
    }
}
~~~

Input objects group related conditions, keep method signatures concise, and make expansion easier. Fields inside an input object must obey GraphQL input type rules: use scalars, enums, lists, or other input objects; never use output objects.

## 6. Default values, nullability, and `null` values

Arguments can declare a default value in the SDL:

~~~graphql
type Book {
    reviews(first: Int = 10): [Review!]!
}
~~~

If the client omits `first`, GraphQL applies the default value `10` before invoking the resolver. Therefore, the Java `Integer first` parameter normally receives `10` when the argument is omitted.

If the client passes `first: 3`, the resolver receives `3`. If the argument is nullable and the client explicitly passes `null`, the resolver receives `null`; the default value does not override an explicit `null`.

| How the client sends it | Value the resolver receives |
| --- | --- |
| Omits `first`, SDL has default `10` | `10` |
| Passes `first: 3` | `3` |
| Passes `first: null` for a nullable argument | `null` |
| Omits a non-null argument without a default | Invalid request |
| Passes `null` for a non-null argument | Invalid request |

If declared as:

~~~graphql
reviews(first: Int! = 10): [Review!]!
~~~

the client can omit the argument because it has a default, but cannot pass `null`. Default and non-null are two complementary rules.

Do not assume a Java parameter is always non-null just because a field has a default somewhere else. Check the exact argument definition on the field in the SDL and consider the case where the client sends explicit `null`.

## 7. Distinguishing omitted from explicit `null` with `ArgumentValue`

For nullable arguments, an application sometimes needs to distinguish between a client omitting the argument and a client passing `null` explicitly.

Spring for GraphQL provides `ArgumentValue<T>` to retain this information.

Example SDL:

~~~graphql
type Book {
    reviews(minRating: Int): [Review!]!
}
~~~

Resolver:

~~~java
import org.springframework.graphql.data.ArgumentValue;

@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(
        Book book,
        @Argument("minRating") ArgumentValue<Integer> minRating) {

    if (minRating.isOmitted()) {
        return reviewService.findAllByBook(book.id());
    }

    if (minRating.value() == null) {
        return reviewService.findWithoutRatingFilter(book.id());
    }

    return reviewService.findWithMinimumRating(
            book.id(),
            minRating.value()
    );
}
~~~

Three states can be handled separately:

- Omitted: the client did not send `minRating`, so the server uses the default business behavior.
- Explicit `null`: the client sent `minRating` as `null`, which the server may interpret as applying no filter.
- Value present: the server applies the rating filter condition.

Not every API needs to distinguish the first two states. If omitted and `null` mean the same thing, a regular nullable Java parameter is simpler. Only use `ArgumentValue` when this distinction carries business meaning.

For nested input objects, you can also use `ArgumentValue` on fields where omitted vs. `null` must be distinguished:

~~~java
public record ReviewFilterInput(
        ArgumentValue<Integer> minRating,
        ArgumentValue<Boolean> verifiedOnly
) {
}
~~~

Test binding for omitted, `null`, and populated cases against the Spring for GraphQL version used by your project.

## 8. Using arguments for pagination and filtering

Nested fields often return lists that can grow large. Arguments are the right place to limit element counts or select a page.

Example of offset pagination:

~~~graphql
type Book {
    id: ID!
    reviews(first: Int = 20, offset: Int = 0): [Review!]!
}
~~~

Resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(
        Book book,
        @Argument("first") Integer first,
        @Argument("offset") Integer offset) {

    int safeFirst = first == null ? 20 : Math.min(Math.max(first, 1), 100);
    int safeOffset = offset == null ? 0 : Math.max(offset, 0);

    return reviewService.findPage(
            book.id(),
            safeFirst,
            safeOffset
    );
}
~~~

Capping `first` on the server prevents clients from requesting an excessive amount of data. Do not rely solely on the default value in the SDL, because a client can still pass a huge or negative number.

For frequently changing data or large lists, cursor pagination is usually more stable than offset pagination. Example:

~~~graphql
type Book {
    id: ID!
    reviews(first: Int = 20, after: String): ReviewConnection!
}

type ReviewConnection {
    edges: [ReviewEdge!]!
    pageInfo: PageInfo!
}

type ReviewEdge {
    cursor: String!
    node: Review!
}

type PageInfo {
    hasNextPage: Boolean!
    endCursor: String
}
~~~

The `after` argument indicates the position from which to continue after the previous cursor. The server must validate the cursor and apply a deterministic sort order to avoid duplicates or skipped items when data changes.

Arguments can also control filtering by status, time range, language, or sort order. Each parameter must have clear semantics and be validated on the server.

## 9. The same nested field invoked for multiple parent objects

When a client queries a list of books and selects `reviews`, GraphQL resolves the `reviews` field for every `Book` in the list:

~~~graphql
query {
    books {
        id
        reviews(first: 3, minRating: 4) {
            id
            rating
        }
    }
}
~~~

If `books` returns 50 objects, the `Book.reviews` resolver may be invoked 50 times. Each invocation receives a different `Book` source but the same arguments `first = 3` and `minRating = 4`.

This highlights the roles of the source object and arguments:

- The source object changes for each `Book`.
- The arguments come from the same field location in the operation, so they share the same values for every `Book` in this execution.
- Results must be loaded specifically for each `Book` ID and filter conditions.

If the resolver calls a repository once per `Book`, the request can run into the N+1 problem.

## 10. Avoiding N+1 when a nested field has arguments

Example of a naive resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(
        Book book,
        @Argument("first") Integer first,
        @Argument("minRating") Integer minRating) {

    return reviewRepository.findByBookIdAndRating(
            book.id(),
            minRating,
            PageRequest.of(0, first)
    );
}
~~~

If there are 50 `Book` objects, this implementation can trigger 50 review queries. You can use `DataLoader` or batching to load data in groups.

When results depend on arguments, the data-loading key must capture every factor that affects the result. For example, a key can include:

~~~java
public record ReviewBatchKey(
        String bookId,
        Integer first,
        Integer minRating
) {
}
~~~

If you only use `bookId` as the key while the result also depends on `first` or `minRating`, the cache can return the wrong result for two calls with different conditions.

A batching strategy can:

1. Collect keys containing `bookId` and filter conditions.
2. Group keys by compatible condition sets.
3. Query data in batches.
4. Distribute results back to the right keys.
5. Preserve ordering and item limits per key.

`DataLoader` is typically scoped per request to avoid sharing cached data across different requests. Never use a global cache for results that depend on user identity or access permissions.

`@BatchMapping` is a convenient way to batch field resolution across multiple source objects. When a field has arguments, ensure the batching strategy still applies the arguments properly and does not mix results across different conditions. For complex filtering/pagination logic, you may need a `DataLoader` with a composite key or a purpose-built repository query.

## 11. Validating and securing arguments

All arguments are client-supplied and must be treated as untrusted data.

For example, `first` is an `Int`, yet GraphQL does not automatically constrain it between 1 and 100. The resolver or service must validate:

- Maximum page size limit.
- Non-negative offset.
- Enum values within the published schema set.
- Start time is not greater than end time.
- Filters do not expose data outside what the user is authorized to view.

Never use client-sent `tenantId`, `ownerId`, or user IDs as the sole basis for access control decisions. The server must obtain identity from the security context and verify permissions on each resource.

If a nested field returns sensitive information, read permissions must be checked in the corresponding resolver or service. The fact that a client does not include that field in a selection set is not a security boundary.

## 12. Testing field mappings with arguments using `GraphQlTester`

You can use `GraphQlTester` to test operations that pass arguments into nested fields:

~~~java
@Test
void filtersReviewsByArguments() {
    graphQlTester.document("""
            query BookReviews($first: Int!, $minRating: Int) {
                books {
                    reviews(first: $first, minRating: $minRating) {
                        id
                        rating
                    }
                }
            }
            """)
        .variable("first", 3)
        .variable("minRating", 4)
        .execute()
        .path("books[0].reviews[0].rating")
        .entity(Integer.class)
        .isEqualTo(5);
}
~~~

This is an illustrative example; the test needs an appropriate schema and data, along with configured services/repositories or mocks matching your project's test context.

You should test these scenarios:

- Arguments passed directly as literals.
- Arguments passed via variables.
- Omitted arguments when the SDL defines a default.
- Nullable arguments passed explicit `null`.
- Non-null arguments missing or receiving `null`.
- Input objects with omitted fields and `null` fields.
- `first` equal to 0, negative numbers, or exceeding the limit.
- Filters returning an empty list.
- Different `Book` sources receiving their respective review results.
- `DataLoader` or batch resolvers not mixing results across different argument sets.

You can use mocks or spies to verify the service receives the expected `Book` ID and arguments. For performance testing, count repository invocations when querying multiple `Book` objects to catch N+1 issues.

## 13. Common issues

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `@Argument` receives `null` | Argument name in annotation does not match the SDL or client omitted the value. | Cross-check argument names, operation, and variables. |
| Receives parent field's argument by mistake | Confused argument scope across selection set levels. | Read arguments on the exact field mapped by the resolver. |
| Source object is `null` or wrong type | Mapping mismatches parent type or method source parameter is wrong. | Check `typeName`, `field`, and source type. |
| Default is not applied | Client may have sent explicit `null` or the SDL default is missing on that field. | Inspect the schema and actual request payload. |
| Cannot distinguish omitted from `null` | Using a regular nullable Java type when business logic needs presence info. | Use `ArgumentValue<T>`. |
| Field returns too much data | Page size is uncapped or arguments are not validated. | Enforce server-side limits and use pagination. |
| Nested resolver runs many queries | Each source object triggers a separate query. | Use `DataLoader` or appropriate batching. |
| `DataLoader` returns the wrong result | Cache key omits arguments that affect the result. | Use a composite key and an appropriate cache scope. |
| Users view unauthorized data | Checking arguments only without checking resource authorization. | Enforce server-side authorization based on the security context. |

When debugging, check the SDL first to identify the field and arguments, then inspect the operation sent by the client. Next, verify the source object, `@Argument` names, post-default/coercion values, and service calls. If results are accurate but slow with many parent objects, inspect query counts and batching.

## 14. Workflow for implementing a field with arguments

When adding arguments to a nested field, follow this sequence:

1. Identify which parent type owns the field and what data needs control.
2. Declare the arguments in the SDL with appropriate types, nullability, and defaults.
3. Choose scalar, enum, or input object based on parameter complexity.
4. Write `@SchemaMapping` for the right type and field.
5. Receive the source object as a resolver parameter and arguments with `@Argument`.
6. Use `ArgumentValue<T>` if omitted must be distinguished from explicit `null`.
7. Validate limits, filters, and access permissions on the server.
8. Design pagination if the field returns a list.
9. Check for N+1 and choose `DataLoader` or batching when needed.
10. Write `GraphQlTester` tests for valid, `null`, omitted, and boundary argument cases.
11. Measure repository call counts across multiple parent objects.

## 15. Key points to remember

- Arguments can be declared on nested fields, not just root `Query` or `Mutation` fields.
- Arguments belong to the field where they are declared; parent field arguments are not automatically passed down to child fields.
- `@SchemaMapping` maps a nested field; the source object is typically the first parameter of the method.
- `@Argument` binds an argument of the current field to a Java parameter.
- Arguments can be scalars, enums, lists, or input objects.
- Defaults are applied when an argument is omitted; explicit `null` remains `null` if the argument is nullable.
- `ArgumentValue<T>` preserves the distinction between omitted and explicit `null`.
- Use arguments for filtering, sorting, and pagination, and always enforce limits on the server.
- Nested resolvers can cause N+1; `DataLoader` and batching must include arguments in the loading key when results depend on them.
- Arguments do not replace authorization; the server must verify permissions on resources.

Mapping fields with arguments lets GraphQL clients control data at the exact field level, especially for nested relationships with filtering and pagination. Combining the source object, `@SchemaMapping`, `@Argument`, validation, and proper batching enables a Spring for GraphQL application to provide a flexible API while staying performant and secure.
