# Path of a failing field in a GraphQL response

In GraphQL, an operation can resolve many nested fields and return data across multiple levels. When a field encounters an error during execution, the corresponding entry in the `errors` array usually has a `path` property indicating the exact position of that field in the response. Clients use path to link the error to the exact affected piece of data, even when the query uses aliases, lists, or fragments.

`path` is a path inside the GraphQL result, not a path to a field in the schema and not a line/column position in the query. It describes response keys and list element indices matching the exact structure of the returned data. Understanding the difference between `path` and `locations` helps the server produce contextual errors, while clients can display errors on the right field without parsing message text.

After this lesson, you will be able to:

- Read `path` in a GraphQL error.
- Understand segments in the form of field names and list indices.
- Determine the effect of aliases on path.
- Understand path when a field is inside a nested object, list, or fragment.
- Distinguish `path` from `locations` and `extensions`.
- Understand why path still points to the original field when null propagation bubbles errors up to a parent.
- Create GraphQL errors with accurate paths in Spring for GraphQL.
- Test and use path on the client to pinpoint the exact failing part of a response.

## 1. What is Path?

`path` is an array of segments describing the traversal from the root of the response to the field that raised the execution error. A segment can be:

- A string: the response key of a field.
- An integer: the 0-based index of an element in a list.

Example query:

```graphql
query {
    book(id: "book-42") {
        title
        author {
            name
        }
    }
}
```

If the `author` resolver fails, the GraphQL error may contain:

```json
{
  "message": "Author could not be loaded",
  "path": ["book", "author"]
}
```

If `author` loaded successfully but the `name` resolver fails, path might be:

```json
["book", "author", "name"]
```

Path starts from the field on the root operation and proceeds through each object level down to the failing field. It helps clients pinpoint the exact spot where the error occurred in the response tree.

## 2. Path uses response keys, not necessarily schema field names

GraphQL allows aliases to rename fields in the response. When an alias is used, path contains the alias because that is the key appearing in the response.

For example:

```graphql
query {
    featuredBook: book(id: "book-42") {
        title
        writer: author {
            name
        }
    }
}
```

If the `author` field fails, path is:

```json
["featuredBook", "writer"]
```

If the `name` field fails, path is:

```json
["featuredBook", "writer", "name"]
```

In the schema, the actual fields are still `Query.book` and `Book.author`. However, the response keys chosen by the client are `featuredBook` and `writer` respectively. Therefore, clients must use path to look up the response object rather than replacing segments with schema field names.

This is especially important when the same field is queried multiple times with different arguments:

```graphql
query {
    newest: books(sort: NEWEST) {
        id
    }
    popular: books(sort: POPULAR) {
        id
    }
}
```

If an element in `popular` fails, path starts with `popular`, not `books`. Aliases let clients distinguish two branches calling the same schema field.

## 3. Path contains list indices

When a field is inside a list, path contains the index of the element where the error occurred. Indices start at `0`.

Query:

```graphql
query {
    books {
        id
        author {
            name
        }
    }
}
```

If `author` of the third element fails, path looks like:

```json
["books", 2, "author"]
```

Explanation of each segment:

| Segment | Meaning |
| --- | --- |
| `"books"` | Root response field `books` |
| `2` | Third element in the `books` list |
| `"author"` | Field `author` of that element |

If the `Author.name` resolver fails, path has one more trailing segment:

```json
["books", 2, "author", "name"]
```

If lists are nested, path can contain multiple indices:

```graphql
query {
    departments {
        teams {
            members {
                displayName
            }
        }
    }
}
```

For example, an error on `displayName` of the first member, in the second team, in the third department:

```json
["departments", 2, "teams", 1, "members", 0, "displayName"]
```

Clients must preserve the data type of each segment. Do not convert all segments to strings because integers represent list indices, not property names.

## 4. Path in nested objects

With multiple object levels, each field response key adds another segment. For example:

```graphql
query {
    order(id: "order-9") {
        customer {
            address {
                city
            }
        }
    }
}
```

If the `city` resolver fails, path is:

```json
["order", "customer", "address", "city"]
```

If the `address` resolver fails before GraphQL can resolve `city`, path stops at:

```json
["order", "customer", "address"]
```

Path points to the field that actually raised the error. It does not list child fields that GraphQL could not resolve after the parent failed.

## 5. Path in fragments

Fragments help reuse selection sets or query fields by concrete type, but fragment names do not become segments in path. Path still reflects the response tree.

For example:

```graphql
fragment AuthorFields on Author {
    id
    name
}

query {
    searchResults {
        ... on Book {
            title
        }
        ...AuthorFields
    }
}
```

If `name` fails on the second element of `searchResults`, path might be:

```json
["searchResults", 1, "name"]
```

Path does not contain `AuthorFields` or `... on Author`, because fragments are a way of structuring the document, not object keys in the response. Likewise, inline fragments do not add a segment to path.

## 6. Distinguishing path and locations

Both `path` and `locations` help identify errors, but they describe two different spaces:

| Property | Description | Example |
| --- | --- | --- |
| `path` | Field position in the response tree | `["books", 2, "author"]` |
| `locations` | Position of the related node in the GraphQL document | `[{"line": 5, "column": 9}]` |

Queries can be written across multiple lines or use fragments. `locations` helps tools find the syntax position in the document; `path` helps clients locate the exact data position after execution.

A parse or validation error occurring before execution may have `locations` without `path`, because no response field has been resolved yet. Conversely, execution errors usually have path because GraphQL knows which field is being processed.

Do not use line/column to look up values in the JSON response. Also do not use path to determine which query line to highlight when `locations` is available; the two properties complement each other.

## 7. Distinguishing path and extensions

`extensions` holds implementation- or application-supplied metadata, such as error codes, correlation IDs, or classifications. `path` has a standard structure to pinpoint the response field location; `extensions` does not replace path.

For example:

```json
{
  "message": "Author service is unavailable",
  "path": ["featuredBook", "writer"],
  "extensions": {
    "code": "UPSTREAM_UNAVAILABLE",
    "retryable": true
  }
}
```

Clients can use `path` to mark the `writer` field in the response and use `extensions.code` to choose the corresponding action. Do not stuff a custom path into `extensions` when GraphQL already has the standard `path` property.

Do not put sensitive information such as tokens, stack traces, or SQL into extensions. Error codes should be stable, whereas messages can change or be translated.

## 8. Path points to the original field, even when null propagation bubbles up to a parent

An important point: `path` indicates the location of the original field that caused the error. It does not change to point to a parent made null by non-null propagation.

Suppose the schema is:

```graphql
type Query {
    book(id: ID!): Book!
}

type Book {
    id: ID!
    author: Author!
}

type Author {
    name: String!
}
```

Query:

```graphql
query {
    book(id: "book-42") {
        author {
            name
        }
    }
}
```

If the `name` resolver fails, path is still:

```json
["book", "author", "name"]
```

Because `name`, `author`, and `book` are all non-null, the error can bubble up to the root and the response has `data: null`. However, path does not become `[]`, `null`, or just `book`; it still points to the `name` field where the error was detected.

If `author` is declared nullable (`author: Author`), an error in `name` can turn `author` into null while still preserving `book.id` and other fields. Path is still `["book", "author", "name"]`.

Therefore, clients should not rely solely on the final null position in `data` to infer the root failing field. Use `errors[].path` to determine where the execution error originated.

## 9. Request errors typically have no path

Path is meaningful once GraphQL has started execution and knows which field failed. Pre-execution errors such as parse, validation, or variable coercion errors typically have no path.

Example query calling a non-existent field:

```graphql
query {
    book(id: "book-42") {
        titel
    }
}
```

GraphQL may return:

```json
{
  "errors": [
    {
      "message": "Cannot query field 'titel' on type 'Book'. Did you mean 'title'?",
      "locations": [
        { "line": 4, "column": 9 }
      ]
    }
  ]
}
```

There is no path because `titel` is not a valid field in the schema and no resolver has been executed. The client must handle a document/schema error instead of trying to find a node in `data`.

Thus, when reading GraphQL errors, treat `path` as optional. Do not assume every error object has a path.

## 10. Creating errors with accurate paths in Spring for GraphQL

When an exception occurs inside a resolver, GraphQL execution already has a `DataFetchingEnvironment` containing information about the current field. When building a `GraphQLError`, use the builder taking the environment to attach the location and path of the executing field.

Example with `@GraphQlExceptionHandler`:

```java
@ControllerAdvice
public class GraphQlExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleAuthorUnavailable(
            AuthorServiceUnavailableException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.INTERNAL_ERROR)
                .message("Author service is temporarily unavailable")
                .extensions(Map.of("code", "AUTHOR_SERVICE_UNAVAILABLE"))
                .build();
    }
}
```

`GraphqlErrorBuilder.newError(environment)` obtains the execution location and path from the field currently being processed. GraphQL can place the error into the response alongside data from other fields while applying null propagation according to the SDL.

If you create an error using a builder without an environment, such as `GraphqlErrorBuilder.newError()`, you must supply the required information yourself if you want the error to have path/location. For exceptions raised from a DataFetcher, prefer the builder taking `DataFetchingEnvironment` to avoid constructing an inaccurate path manually.

Do not build paths manually by concatenating field names in a controller. When aliases, list indices, or nested resolvers are involved, schema names alone are insufficient to reconstruct the exact response path.

## 11. Path with DataFetcherExceptionResolver

If the application uses `DataFetcherExceptionResolver` for centralized exception mapping, the resolver also receives `DataFetchingEnvironment` and can build an error bound to the current field.

Example handler skeleton:

```java
@Component
public class AuthorExceptionResolver extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof AuthorServiceUnavailableException) {
            return GraphqlErrorBuilder.newError(environment)
                    .errorType(ErrorType.INTERNAL_ERROR)
                    .message("Author service is temporarily unavailable")
                    .extensions(Map.of("code", "AUTHOR_SERVICE_UNAVAILABLE"))
                    .build();
        }

        return null;
    }
}
```

This is a centralized implementation approach for DataFetcher errors. For exceptions outside its handling scope, the resolver returns `null` so subsequent resolvers can process them according to the contract of `DataFetcherExceptionResolverAdapter` and the Spring for GraphQL version in use.

There is no need to create both a `@GraphQlExceptionHandler` and a `DataFetcherExceptionResolver` for the same exception. Choose a single responsible component so messages, codes, and logging stay consistent.

## 12. Path with aliases and nested resolvers in practice

Consider the query:

```graphql
query Catalog {
    primary: books {
        id
        mainAuthor: author {
            name
        }
    }
    secondary: books {
        id
        mainAuthor: author {
            name
        }
    }
}
```

If the author of the second book in the `secondary` branch fails in the `author` resolver, path might be:

```json
["secondary", 1, "mainAuthor"]
```

If `Author.name` fails, path adds `name`:

```json
["secondary", 1, "mainAuthor", "name"]
```

Path distinguishes the `primary` and `secondary` branches even though both invoke the `books` schema field. It also pinpoints the second element and the alias of the relationship field.

This shows that the server does not need to know which aliases a client will choose when writing resolvers. The GraphQL engine builds path from the current execution and returns it in the error.

## 13. How clients use path to identify failing fields

Clients can traverse `path` to find the corresponding location in response data. General idea:

1. Read `error.path` and check whether it is an array.
2. Start at `data`.
3. For a string segment, access the property by response key.
4. For a number segment, access the list element at that index.
5. Mark the failing field/branch or display a message near that location.

TypeScript example illustrating path traversal:

```typescript
type PathSegment = string | number;

function valueAtPath(data: unknown, path: PathSegment[]): unknown {
  return path.reduce<unknown>((current, segment) => {
    if (current == null) return undefined;

    if (typeof segment === "number" && Array.isArray(current)) {
      return current[segment];
    }

    if (typeof segment === "string" && typeof current === "object") {
      return (current as Record<string, unknown>)[segment];
    }

    return undefined;
  }, data);
}
```

This is an illustrative example; real clients must handle missing paths, null data, invalid segments, and response structures normalized into a cache.

Do not use path as a long-term ID for an entity. Path is only meaningful within the response of the current operation; lists may change order between calls and aliases may differ across queries.

## 14. Path and normalized client caches

Some GraphQL clients store objects in a normalized cache by ID rather than keeping the raw response tree. In that case, path still describes the position in the operation's raw response, which does not necessarily map directly to internal keys in the normalized cache.

For example, the path:

```json
["books", 2, "author", "name"]
```

can point to `books[2].author.name` in the raw response. After normalization, the client may store `Book:book-42` and `Author:author-9` as separate records. The client needs operation metadata and the mapping from response to cache to mark the error accurately.

Do not assume every client library handles `errors[].path` the same way. Check how your specific library exposes GraphQL errors and partial data, especially when using optimistic updates or cache normalization.

## 15. Testing path with GraphQlTester

`GraphQlTester` lets you execute a document and inspect GraphQL errors. When verifying path, you can read `GraphQLError.getPath()` in assertions:

```java
graphQlTester.document("""
        query {
            featured: books {
                id
                writer: author {
                    name
                }
            }
        }
        """)
    .execute()
    .errors()
    .satisfy(errors -> {
        assertThat(errors).hasSize(1);
        assertThat(errors.get(0).getPath())
                .containsExactly("featured", 0, "writer");
    });
```

If the exception occurs in `Author.name`, the path assertion needs to include `"name"`. The asserted path must match the field that actually throws the error in your test fixture.

Key tests:

1. Errors on root fields have a path containing only the root response key.
2. Errors on nested fields have full parent and child segments.
3. Aliases are used in path instead of schema field names.
4. List indices start at 0 and point to the exact element.
5. Nested lists have multiple integer segments.
6. Inline fragments do not appear as segments in path.
7. Request parse/validation errors may have no path.
8. Null propagation does not alter the path of the original field.
9. Error handlers using `DataFetchingEnvironment` produce accurate paths/locations.
10. Clients handle cases where path is absent.

Create fixtures with multiple elements where one specific element intentionally fails to confirm path has the exact index, rather than only testing a single-element list that always has index 0.

## 16. Common pitfalls

- **Treating path as schema field names:** path uses response keys, so aliases change segments.
- **Converting all segments to strings:** list indices are integers and must keep their type.
- **Counting indices from 1:** GraphQL paths use 0-based list indices.
- **Using locations instead of path:** locations are line/column in the document, not positions in the response.
- **Assuming fragments appear in path:** fragments are not response keys.
- **Assuming path points to a nullified parent:** path keeps the initial field that raised the error even when null propagation bubbles up to an ancestor.
- **Assuming request errors always have path:** parse/validation/coercion errors usually occur before execution.
- **Manually concatenating schema names for path in exception handlers:** error-prone with aliases or list indices; use `DataFetchingEnvironment`.
- **Creating GraphQLError without an execution environment:** errors may lack path/location unless supplied manually.
- **Using path as a long-term ID:** path is meaningful only within a single response.
- **Ignoring partial data:** other fields can still succeed even when one path fails.

## 17. Workflow for reading and handling path

When a GraphQL response contains errors, follow these steps:

1. Check whether `errors` exists and whether each error has `path`.
2. If path is present, read each segment with its proper string or integer type.
3. Use response keys to handle aliases; do not substitute schema field names.
4. Use integer segments to identify list elements, starting at index 0.
5. Use `locations` separately to point to line/column in the document if needed.
6. Use `extensions.code` to classify errors instead of parsing message text.
7. Inspect `data` to see which partial results remain usable or became null due to propagation.
8. On the server, use `DataFetchingEnvironment` when creating GraphQLError from exception resolvers.
9. Test aliases, nested objects, lists, fragments, and non-null propagation.
10. Never persist path as a stable resource or field identifier across operations.

`path` tells GraphQL clients where an error occurred in the response tree. String segments reflect response keys, including aliases; integer segments identify list element positions. `path` differs from `locations` in the query document and continues pointing to the original field when null propagation bubbles nulls up to parents. In Spring for GraphQL, using `DataFetchingEnvironment` when creating errors attaches the exact path and location for the current execution. When clients read path as a typed array and combine it with partial data and error codes, field-level errors can be handled accurately and consistently.

## References

- [GraphQL Specification — Errors](https://spec.graphql.org/October2021/#sec-Errors)
- [GraphQL Specification — Response Format](https://spec.graphql.org/October2021/#sec-Response-Format)
- [GraphQL Java — GraphqlErrorBuilder API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/GraphqlErrorBuilder.html)
- [Spring for GraphQL — Exception Handling](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.exception-handling)
- [Spring for GraphQL — GraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
