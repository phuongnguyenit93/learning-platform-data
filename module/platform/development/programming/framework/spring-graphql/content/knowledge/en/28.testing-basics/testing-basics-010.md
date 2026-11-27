# Asserting Errors with GraphQlTester

A GraphQL response can contain both `data` and `errors`. Therefore, testing an operation is not only checking returned values; tests also need to verify which errors appear, which field each error is attached to, whether the classification code matches, and whether other fields retain partial data. Spring for GraphQL provides `GraphQlTester` with the `errors()` API to test these scenarios.

`errors()` allows verifying that a response has no errors or inspecting the list of `ResponseError` objects to assert expected errors. For errors that are part of the contract, prefer asserting structured properties like `path` and `extensions.code` instead of comparing only the full message. Messages often change in wording or language; paths and error codes are usually more stable for clients.

After this lesson, you will be able to:

- Understand `GraphQlTester.Errors` and the ways to assert errors.
- Verify that an operation has no GraphQL errors.
- Check expected errors using `satisfy(...)`.
- Assert messages, paths, error codes, and metadata in extensions.
- Distinguish request errors from execution errors.
- Verify partial data and null propagation when errors occur.
- Assert multiple errors, aliases, and list indices.
- Organize helpers for consistent error assertions across tests.

## 1. A GraphQL Response Can Contain Both data and errors

A successful response typically contains `data`:

```json
{
  "data": {
    "book": {
      "id": "book-42",
      "title": "Spring GraphQL in Practice"
    }
  }
}
```

When a field encounters an error during execution, GraphQL can still return other fields:

```json
{
  "data": {
    "book": {
      "id": "book-42",
      "title": "Spring GraphQL in Practice",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author service is unavailable",
      "path": ["book", "author"],
      "extensions": {
        "code": "UPSTREAM_UNAVAILABLE"
      }
    }
  ]
}
```

In this example, `book.title` still has data while `book.author` failed. Tests should verify both facts: that the expected error is present and that the `title` field is still returned.

Do not treat every response containing `errors` as a total failure. Likewise, do not ignore `errors` simply because `data` is present. These two sections describe two aspects of the same execution result.

## 2. What Is GraphQlTester.Errors?

After executing an operation, `GraphQlTester.Response.errors()` returns the `GraphQlTester.Errors` API to inspect the GraphQL error list.

```java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "missing") {
                title
            }
        }
        """)
    .execute();

response.errors().satisfy(errors -> {
    assertThat(errors).isNotEmpty();
});
```

`errors()` is not a Java exception; it is the way to access errors in the GraphQL response. This is an important distinction: execution errors are typically represented in response `errors`, without necessarily causing the `execute()` call to throw an exception like connection or transport errors do.

Common verification methods:

- `verify()`: verifies the response has no unhandled GraphQL errors.
- `satisfy(...)`: receives the full error list to write custom assertions.
- `expect(...)`: declares an expected error; the test fails if no error matches the predicate.
- `filter(...)`: ignores acceptable errors; the predicate is not required to match at least one error.

When a test needs to verify a specific error and its properties, `satisfy(...)` is direct and easy to read.

## 3. Verifying a Response Has No Errors

For a query expected to succeed completely, call `verify()`:

```java
@Test
void loadsBookWithoutErrors() {
    graphQlTester.document("""
            query {
                book(id: "book-42") {
                    id
                    title
                }
            }
            """)
        .execute()
        .errors()
        .verify();
}
```

`verify()` fails the test if the response contains unhandled GraphQL errors. Afterward, if needed, you can continue asserting data on the response in the same assertion flow by holding the response in a variable.

Example checking both zero errors and a field value:

```java
@Test
void loadsBookTitle() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
                book(id: "book-42") {
                    title
                }
            }
            """)
        .execute();

    response.errors().verify();
    response.path("book.title")
            .entity(String.class)
            .isEqualTo("Spring GraphQL in Practice");
}
```

Use `verify()` when the operation's contract requires zero errors. If an operation is designed to return partial data alongside expected errors, verify those errors explicitly instead of calling `verify()` mechanically.

## 4. Checking Expected Errors with satisfy

Suppose the service throws `BookNotFoundException` and the exception handler maps it to the message `Book not found` and code `BOOK_NOT_FOUND`.

```java
@Test
void reportsBookNotFound() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
                book(id: "missing") {
                    id
                    title
                }
            }
            """)
        .execute();

    response.errors().satisfy(errors -> {
        assertThat(errors).hasSize(1);
        assertThat(errors.get(0).getMessage())
                .isEqualTo("Book not found");
    });
}
```

`satisfy(...)` lets you use AssertJ to inspect the entire list. Asserting `hasSize(1)` ensures the test does not miss extra errors beyond the expected one.

If the message is public content but not a stable contract, check it partially or prefer checking `extensions.code`. Avoid comparing stack traces or internal messages that depend on database, framework, or environment details.

## 5. Asserting Error Codes in extensions

Applications often place stable error codes in `extensions`, for example:

```json
{
  "message": "Book not found",
  "extensions": {
    "code": "BOOK_NOT_FOUND"
  }
}
```

Test checking the code:

```java
response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    assertThat(errors.get(0).getExtensions())
            .containsEntry("code", "BOOK_NOT_FOUND");
});
```

`extensions` is a metadata map. Assert only keys that the API commits to providing. Do not lock tests to timestamps, trace IDs, or metadata that changes per run unless the test is specifically verifying those values.

Error codes help clients choose actions without parsing `message`. For instance, `BOOK_NOT_FOUND`, `FORBIDDEN`, or `UPSTREAM_UNAVAILABLE` can serve as a machine-readable contract.

## 6. Asserting the Path of the Failing Field

`path` identifies the field in the response tree where an execution error occurred. Example query:

```graphql
query {
    book(id: "book-42") {
        author {
            name
        }
    }
}
```

If the `name` resolver fails, the path may be `["book", "author", "name"]`.

```java
response.errors().satisfy(errors -> {
    assertThat(errors).anySatisfy(error -> {
        assertThat(error.getParsedPath())
                .containsExactly("book", "author", "name");
    });
});
```

Path segments can be string response field keys or integer list indices. Preserve the exact data types when asserting. Do not convert indices into strings.

In Spring for GraphQL, errors received in `GraphQlTester.Errors` are of type `ResponseError`. Use `getParsedPath()` to retrieve the parsed list of `String` and `Integer` segments; `getPath()` returns a string representation.

Paths are a valuable part of the error contract when clients need to highlight the exact failing field in the UI or analyze errors by response branch.

## 7. Aliases Affect the Path

GraphQL aliases change response keys. Paths use aliases, not the original schema field names.

Query:

```graphql
query {
    featured: book(id: "book-42") {
        writer: author {
            name
        }
    }
}
```

If `name` fails, the path is:

```json
["featured", "writer", "name"]
```

Test:

```java
response.errors().satisfy(errors -> {
    assertThat(errors).anySatisfy(error ->
            assertThat(error.getParsedPath())
                    .containsExactly("featured", "writer", "name"));
});
```

If the query changes an alias, the path assertion must change accordingly. Do not use `book.author.name` when the actual response key is `featured.writer.name`.

## 8. Asserting Paths with List Indices

When a field is inside a list element, the path contains a `0`-based index.

```graphql
query {
    books {
        author {
            name
        }
    }
}
```

If the author's `name` for the second book fails, the path may be:

```json
["books", 1, "author", "name"]
```

Test:

```java
response.errors().satisfy(errors -> {
    assertThat(errors).anySatisfy(error ->
            assertThat(error.getParsedPath())
                    .containsExactly("books", 1, "author", "name"));
});
```

Create fixtures with at least two elements to verify the exact index. A test with only one element always sees index `0` and may miss bugs where the server assigns the wrong item.

## 9. Asserting Multiple Errors in the Same Response

A single operation can produce multiple execution errors—for example, two independent fields calling different services and both failing.

```graphql
query Dashboard {
    profile {
        displayName
    }
    recommendations {
        id
    }
    notifications {
        id
    }
}
```

Tests can verify both the error count and the set of error codes:

```java
response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(2);

    assertThat(errors)
            .extracting(error -> error.getExtensions().get("code"))
            .containsExactlyInAnyOrder(
                    "RECOMMENDATIONS_UNAVAILABLE",
                    "NOTIFICATIONS_UNAVAILABLE");
});
```

When error ordering is not part of the contract, use an order-independent assertion. If ordering matters to the application, verify whether GraphQL execution/transport actually guarantees that order before writing tests for it.

Do not assert only `errors().isNotEmpty()` if the test needs to verify the specific error type. An unexpected validation or authorization error would also cause such a broad assertion to pass.

## 10. Distinguishing Request Errors and Execution Errors

Request errors occur before GraphQL executes resolvers—for instance, a query requesting a nonexistent field or an invalid variable. Execution errors occur while resolvers are running.

| Category | Example | Path |
| --- | --- | --- |
| Parse error | Invalid SDL document/query syntax | Usually absent |
| Validation error | Querying a nonexistent field | Usually absent |
| Variable coercion error | Sending a string for `Int!` | Usually absent |
| Execution error | Service fails when resolving `book.author` | Usually has a path |

Validation error test:

```java
@Test
void rejectsUnknownField() {
    graphQlTester.document("""
            query {
                book(id: "book-42") {
                    titel
                }
            }
            """)
        .execute()
        .errors()
        .satisfy(errors -> {
            assertThat(errors).anySatisfy(error ->
                    assertThat(error.getMessage())
                            .contains("Cannot query field"));
            assertThat(errors.get(0).getParsedPath()).isEmpty();
        });
}
```

Do not require every error to have a path. Request errors usually have no specific executing field to attach a path to.

## 11. Checking Null Propagation Alongside Errors

When a non-null field produces an error, GraphQL bubbles null up to the nearest nullable parent. The error path still points to the original field.

Suppose the schema is:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    title: String!
    author: Author
}

type Author {
    name: String!
}
```

If `Author.name` fails, the `Author` object becomes null; because `Book.author` is nullable, the `Book` object remains intact. A test can verify:

```java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "book-42") {
                title
                author {
                    name
                }
            }
        }
        """)
    .execute();

response.errors().satisfy(errors -> {
    assertThat(errors).anySatisfy(error ->
            assertThat(error.getParsedPath())
                    .containsExactly("book", "author", "name"));
}).path("book", book -> {
    book.path("title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL in Practice");
    book.path("author").valueIsNull();
});
```

Tests must match the actual nullability in SDL. If `Query.book` is also non-null, the error can propagate to root and `data` becomes null; in that case, `book.title` cannot be read.

## 12. Asserting Partial Data and Expected Errors

A good test for partial data verifies all three things:

1. The expected error is present.
2. `path` and `extensions.code` point to the exact failing field.
3. Independent fields still contain data.

Example:

```java
@Test
void returnsBookTitleWhenAuthorLookupFails() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
                book(id: "book-42") {
                    title
                    author {
                        name
                    }
                }
            }
            """)
        .execute();

    response.errors().satisfy(errors -> {
        assertThat(errors).singleElement().satisfies(error -> {
            assertThat(error.getExtensions())
                    .containsEntry("code", "AUTHOR_UNAVAILABLE");
            assertThat(error.getParsedPath())
                    .containsExactly("book", "author");
        });
    }).path("book", book -> {
        book.path("title")
            .entity(String.class)
            .isEqualTo("Spring GraphQL in Practice");
        book.path("author").valueIsNull();
    });
}
```

This example assumes the `author` resolver throws directly, the `author` field is nullable, and the exception handler provides the `AUTHOR_UNAVAILABLE` code. If the error occurred deeper at `Author.name`, the path would include an additional `name` segment.

## 13. Declaring Expected Errors or Filtering Acceptable Errors

When a test requires a specific error to appear, use `expect(...)`:

```java
response.errors()
        .expect(error -> "BOOK_NOT_FOUND".equals(
                error.getExtensions().get("code")))
        .verify();
```

`expect(...)` marks errors matching the predicate as expected, requires at least one error to match, and then `verify()` still fails the test if unexpected errors remain.

`filter(...)` has different semantics: it ignores matching errors if they appear, without requiring them to appear. This suits warnings/notifications that may or may not be present:

```java
response.errors()
        .filter(error -> "DEPRECATION_NOTICE".equals(
                error.getExtensions().get("code")))
        .verify();
```

In this example, `verify()` checks that no errors remain outside the allowed `DEPRECATION_NOTICE` group. If you need to confirm that `BOOK_NOT_FOUND` is actually present, use `expect(...)` or `satisfy(...)` with explicit assertions.

If the goal is to thoroughly inspect the error list, `satisfy(...)` is clearer because the callback receives the list to assert count, code, and path. Avoid using a filter to hide all errors with an overly broad predicate like `error -> true`.

## 14. Distinguishing Expected Errors and Unexpected Errors

Some tests intentionally trigger errors. That does not mean the test should ignore all errors. Clearly define which errors are expected and ensure unexpected errors still fail the test.

For example, an operation may accept `BOOK_NOT_FOUND`, but not `INTERNAL_ERROR` or `FORBIDDEN`:

```java
response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    assertThat(errors.get(0).getExtensions())
            .containsEntry("code", "BOOK_NOT_FOUND");
});
```

Asserting both count and code makes the test stricter than checking only that at least one error exists. If the response includes an extra unexpected error, the test fails.

For queries spanning multiple independent branches, assert the expected set of codes using `containsExactlyInAnyOrder`. This permits multiple expected errors without ignoring unfamiliar ones.

## 15. Creating Reusable Assertion Helpers

If many tests need to check the same error code, you can create a small helper:

```java
import org.springframework.graphql.ResponseError;

static void assertSingleGraphQlError(
        GraphQlTester.Response response,
        String expectedCode,
        List<?> expectedPath) {

    response.errors().satisfy(errors -> {
        assertThat(errors).hasSize(1);
        ResponseError error = errors.get(0);
        assertThat(error.getExtensions())
                .containsEntry("code", expectedCode);
        assertThat(error.getParsedPath()).containsExactlyElementsOf(expectedPath);
    });
}
```

Usage:

```java
assertSingleGraphQlError(
        response,
        "AUTHOR_UNAVAILABLE",
        List.of("book", "author"));
```

Helpers should keep assertions specific and preserve context when tests fail. If error messages need checking in some tests, add a parameter or write a separate assertion in those tests instead of turning the helper into an obscure generic framework.

## 16. Asserting Classification and Error Type

Spring for GraphQL can classify errors using `ErrorType`, such as `BAD_REQUEST`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, or `INTERNAL_ERROR`. Applications may use this classification alongside custom error codes in `extensions`.

When classification is part of the contract, you can assert it:

```java
response.errors().satisfy(errors -> {
    assertThat(errors).singleElement().satisfies(error -> {
        assertThat(error.getErrorType())
                .isEqualTo(ErrorType.NOT_FOUND);
        assertThat(error.getExtensions())
                .containsEntry("code", "BOOK_NOT_FOUND");
    });
});
```

If the project does not commit to a specific `ErrorType` for clients, assert `extensions.code` or the agreed public message. Avoid coupling tests to implementation details of an exception resolver if those details are not part of the contract.

## 17. Asserting Authorization Errors

When method security denies a field during GraphQL execution, the response may include a GraphQL error with code `FORBIDDEN`:

```java
@Test
@WithMockUser(authorities = "PROFILE_READ")
void deniesBookRead() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
                books {
                    id
                }
            }
            """)
        .execute();

    response.errors().satisfy(errors -> {
        assertThat(errors).singleElement().satisfies(error -> {
            assertThat(error.getExtensions())
                    .containsEntry("code", "FORBIDDEN");
        });
    });
}
```

Tests must enable method security in the Spring context and configure an exception handler to map access denied exceptions to the expected code. If a request is blocked at the HTTP security filter before GraphQL execution starts, `ExecutionGraphQlServiceTester` cannot verify an HTTP 401/403 response; test over HTTP transport instead.

## 18. Asserting Errors in Mutations

Mutations can fail due to validation, conflicts, missing permissions, or dependency failures. Tests should distinguish GraphQL execution errors from business errors placed in the payload.

If the API uses GraphQL errors:

```java
response.errors().satisfy(errors -> {
    assertThat(errors).singleElement().satisfies(error -> {
        assertThat(error.getExtensions())
                .containsEntry("code", "ORDER_CONFLICT");
    });
});
```

If the API represents business errors with `userErrors` in the payload, the response may have no GraphQL errors:

```java
response.errors().verify()
        .path("createOrder.userErrors[0].code")
        .entity(String.class)
        .isEqualTo("COUPON_EXPIRED");
```

Do not assert `errors()` for a business error designed as payload data and conclude the server is broken. Test according to the chosen contract and keep error representation consistent.

## 19. Checking Errors in Lists and Multiple Nested Fields

A response may contain multiple errors on different elements. For example, a query returns a list of books, while two author resolvers fail at different indices.

```java
import org.springframework.graphql.ResponseError;

response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(2);
    assertThat(errors)
            .extracting(ResponseError::getParsedPath)
            .containsExactlyInAnyOrder(
                    List.of("books", 0, "author"),
                    List.of("books", 2, "author"));
});
```

This assertion checks the set of paths without relying on order. If error ordering is something the test must verify, use `containsExactly(...)` and ensure that ordering is part of committed behavior.

With aliases inside lists:

```graphql
query {
    catalog: books {
        writer: author {
            name
        }
    }
}
```

The corresponding path may be `["catalog", 1, "writer", "name"]`. Tests should assert the actual response key rather than the schema field name.

## 20. Checking Request Errors Without a Path

Request errors such as field validation errors or variable coercion errors happen before resolvers run. The path typically has no value.

```java
@Test
void reportsValidationErrorWithoutPath() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
                book(id: "book-42") {
                    unknownField
                }
            }
            """)
        .execute();

    response.errors().satisfy(errors -> {
        assertThat(errors).isNotEmpty();
        assertThat(errors).allSatisfy(error ->
                assertThat(error.getParsedPath()).isEmpty());
    });
}
```

Do not enforce a mandatory path assertion on all errors. Execution errors usually have a path; request errors may omit it. Tests should reflect the error stage.

If you need to confirm the resolver did not run, use a mock/spy service and verify zero invocations. Checking only that the path is null/empty does not prove the resolver was never called.

## 21. Distinguishing GraphQL Errors from Transport Errors

`GraphQlTester.Errors` checks errors inside the GraphQL response. Transport errors such as timeouts, connection refused, TLS handshake failures, or HTTP responses that cannot be parsed as a GraphQL response may be represented as exceptions from the client/tester rather than items in `errors`.

| Error Type | Where to Check |
| --- | --- |
| Resolver throws an exception | `response.errors()` |
| Query validation error | `response.errors()` |
| Variable coercion error | `response.errors()` |
| Field authorization during execution | `response.errors()` |
| HTTP 503 before GraphQL response | HTTP/client exception or transport response |
| Connection timeout | Reactor/client exception |
| WebSocket disconnect | WebSocket client/test lifecycle |

Do not use `errors()` to check network errors when no GraphQL response exists. With HTTP testers, you may need to assert status codes and bodies separately. With execution testers, transport is outside the scope of the test.

## 22. Common Errors When Asserting Errors

- **Checking only `isNotEmpty()`:** any error makes the test pass, including unexpected ones.
- **Overly detailed message comparison:** messages can change by language or implementation.
- **Not checking error count:** extra errors can slip past unnoticed.
- **Requiring every error to have a path:** request errors typically have no path.
- **Using schema field names instead of aliases in paths:** paths use response keys.
- **Converting list indices to strings:** path index segments are integers.
- **Ignoring partial data:** one failing field does not mean all data failed.
- **Confusing null with errors:** nullable fields can be null without a GraphQL error.
- **Using GraphQL errors to assert payload business errors:** `userErrors` can be normal data.
- **Using errors() to check timeouts/HTTP failures:** those are transport errors, not GraphQL errors.
- **Filtering errors too broadly:** filters can hide unexpected failures.
- **Testing only execution errors:** request validation/coercion and transport must also be tested at their proper layers.

## 23. Workflow for Asserting GraphQL Errors

When writing tests for an operation that may produce errors, follow these steps:

1. Determine whether the operation is expected to have zero errors or expected errors.
2. If zero errors, call `response.errors().verify()`.
3. If errors are expected, use `satisfy(...)` to verify count and properties.
4. Assert `extensions.code` when error codes are part of the API contract.
5. Assert `path` using actual response keys, aliases, and list indices.
6. Assert `locations` only when verifying positions in the document.
7. Distinguish pathless request errors from path-bearing execution errors.
8. Verify partial data and null propagation according to SDL.
9. Never ignore unexpected errors when using filters or helpers.
10. Test transport errors at the HTTP/WebSocket/client layer instead of `errors()`.

`GraphQlTester.Errors` enables structured verification of GraphQL errors. `verify()` fits operations expected to succeed completely; `satisfy(...)` fits when tests need to confirm expected errors by count, code, path, or classification. Combining error assertions with data, null propagation, and distinguishing request/execution/transport errors helps tests catch real bugs while preserving GraphQL's partial data behavior.

## References

- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL — GraphQlTester API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/GraphQlTester.html)
- [Spring for GraphQL — GraphQlTester.Errors API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/GraphQlTester.Errors.html)
- [GraphQL Specification — Errors](https://spec.graphql.org/October2021/#sec-Errors)
- [GraphQL Specification — Response Format](https://spec.graphql.org/October2021/#sec-Response-Format)
