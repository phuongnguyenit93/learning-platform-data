# Error Filter

When testing a GraphQL API with Spring for GraphQL, a response may contain both `data` and `errors`. Some tests intentionally trigger errors or verify fields that can fail while other fields still return data. If you use `GraphQlTester` and call `verify()` directly, any GraphQL error not declared as expected will cause the assertion to fail.

**Error filter** is `GraphQlTester`'s mechanism to mark certain response errors as expected, allowing the test to continue inspecting the remaining data. Spring for GraphQL provides three ways to handle errors within a response: `filter(...)`, `expect(...)`, and `satisfy(...)`. In addition, the builder offers `errorFilter(...)` to apply a shared predicate to every request sent by that tester.

This lesson focuses on the scope and usage of these APIs, how to write predicates narrow enough not to hide regressions, and how to test partial data alongside GraphQL errors.

## 1. Why Do We Need Error Filters?

GraphQL can return partial data if one field encounters an error while other fields still execute successfully.

Example schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    recommendation: Recommendation
}

type Recommendation {
    id: ID!
    reason: String!
}
~~~

Suppose `book` and `title` retrieve data successfully, while the recommendation service is temporarily unavailable. The response might look like:

~~~json
{
    "data": {
        "book": {
            "id": "book-42",
            "title": "Spring for GraphQL",
            "recommendation": null
        }
    },
    "errors": [
        {
            "message": "Recommendation service is unavailable",
            "path": ["book", "recommendation"],
            "extensions": {
                "code": "RECOMMENDATION_UNAVAILABLE"
            }
        }
    ]
}
~~~

A test that only wants to confirm `book.title` can still be read needs to handle the error on the `recommendation` field. Without declaring that error as expected, response verification can fail before the test reaches the data path.

Example:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-42") {
                id
                title
                recommendation {
                    id
                }
            }
        }
        """)
        .execute()
        .errors()
        .filter(error ->
                "book.recommendation".equals(error.getPath())
                        && "RECOMMENDATION_UNAVAILABLE".equals(
                                error.getExtensions().get("code"))
        )
        .verify()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
~~~

An error filter lets the test clearly identify which error is acceptable in that test context. Errors not matching the predicate remain unhandled and cause `verify()` to fail.

## 2. Error Filters Operate on the Testing Side

Distinguish two separate concerns:

- **Server error handling:** resolvers, `DataFetcherExceptionResolver`, or `@GraphQlExceptionHandler` decide how exceptions become GraphQL errors.
- **Test error filtering:** `GraphQlTester` decides which errors are considered expected when verifying a response.

`filter(...)` does not remove errors from the server response, modify `data`, prevent resolvers from throwing exceptions, or change API behavior for real clients. It only adjusts how `GraphQlTester` verifies the response in the current test.

Therefore, never use an error filter as a way to fix server bugs. If the production API emits unexpected errors, fix the resolver, service, or error mapping. Filters are only suitable when a test knows a specific error may appear and wants to focus on asserting another part of the response.

## 3. Preparing GraphQlTester

Error filter APIs belong to `spring-graphql-test`. Add the dependency in test scope:

~~~groovy
dependencies {
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
~~~

With Maven:

~~~xml
<dependency>
    <groupId>org.springframework.graphql</groupId>
    <artifactId>spring-graphql-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Spring Boot dependency management can manage compatible versions. There is no need to declare a separate version if the project already uses Spring Boot dependency management.

`GraphQlTester` provides a unified testing workflow. You can create testers from different extensions:

| Tester | Scope |
| --- | --- |
| `ExecutionGraphQlServiceTester` | Calls the server-side execution service directly |
| `WebGraphQlTester` | Tests `WebGraphQlHandler` and the interceptor chain |
| `HttpGraphQlTester` | Tests over HTTP |
| `WebSocketGraphQlTester` | Tests over WebSocket |
| `RSocketGraphQlTester` | Tests over RSocket |

Handling `errors()` is part of the shared API, so the same predicate can be reused across tester types. How the tester is created depends on the transport being tested.

## 4. Lifecycle of Checking Errors in a Response

A test request typically looks like:

~~~java
graphQlTester.document(document)
        .execute()
        .errors()
        .filter(error -> /* predicate */)
        .verify()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
~~~

Steps:

1. `document(...)` provides the GraphQL document.
2. `execute()` sends the request and receives the response.
3. `errors()` opens the declaration of how to handle GraphQL errors in the response.
4. `filter(...)`, `expect(...)`, or `satisfy(...)` handles errors according to the test's goal.
5. `verify()` confirms no unexpected errors remain.
6. `path(...)` moves on to asserting data in the `data` section.

You must declare error handling before navigating to `path(...)`. If a test jumps directly to a data path while the response contains unhandled errors, `GraphQlTester` will not automatically ignore those errors.

## 5. Using errors().filter(...) to Ignore Known Errors

`filter(Predicate<ResponseError>)` marks errors matching the predicate as expected and ignores them during `verify()` or when navigating to data paths.

Example:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-42") {
                id
                title
                recommendation {
                    id
                }
            }
        }
        """)
        .execute()
        .errors()
        .filter(error -> error.getMessage()
                .equals("Recommendation service is unavailable"))
        .verify()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
~~~

In this example, an error with the exact specified message will not cause `verify()` to fail. If the response does not contain that error, the test still succeeds; `filter(...)` does not require the predicate to match at least one error.

This behavior is appropriate when an error may or may not appear depending on test data, while the main goal is verifying another part of the response. If a test must assert that the error definitely occurred, use `expect(...)`.

## 6. Using errors().expect(...) When an Error Must Appear

`expect(Predicate<ResponseError>)` also marks matching errors as expected. Unlike `filter(...)`, `expect(...)` requires at least one matching error; if none exists, the assertion fails.

Example verifying that the recommendation service failed as planned:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-42") {
                id
                title
                recommendation {
                    id
                }
            }
        }
        """)
        .execute()
        .errors()
        .expect(error ->
                "book.recommendation".equals(error.getPath())
                        && "RECOMMENDATION_UNAVAILABLE".equals(
                                error.getExtensions().get("code"))
        )
        .verify()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
~~~

This test simultaneously verifies:

- There must be at least one error with code `RECOMMENDATION_UNAVAILABLE` at path `book.recommendation`.
- The matching error is considered expected.
- Any other errors not matching the predicate still fail `verify()`.
- The `book.title` field must still return the right data.

`expect(...)` does not guarantee that only one matching error exists. If you need to assert the exact error count, use `satisfy(...)` and assert on the error list.

## 7. Using errors().satisfy(...) to Inspect the Entire List

`errors().satisfy(Consumer<List<ResponseError>>)` lets you inspect the error list directly using AssertJ or another assertion library.

Example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

graphQlTester.document("""
        query {
            book(id: "book-42") {
                id
                title
                recommendation {
                    id
                }
            }
        }
        """)
        .execute()
        .errors()
        .satisfy(errors -> {
            assertThat(errors).hasSize(1);
            assertThat(errors.get(0).getPath())
                    .isEqualTo("book.recommendation");
            assertThat(errors.get(0).getExtensions())
                    .containsEntry("code", "RECOMMENDATION_UNAVAILABLE");
        })
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
~~~

Once the consumer completes, `satisfy(...)` considers all errors inspected and marks them as filtered. Thus, the test can continue to data paths.

This is very useful when asserting multiple error properties such as path, message, code, and count. However, because all errors are treated as handled, the consumer must assert thoroughly. If it checks only one error and ignores others, the test could inadvertently accept an invalid response.

## 8. Comparing filter, expect, and satisfy

| API | Condition for Test to Continue | Requires Error to Appear? | Best Suited When |
| --- | --- | --- | --- |
| `filter(predicate)` | Matching errors are ignored; other errors must still be handled | No | Known error may or may not appear |
| `expect(predicate)` | Matching errors are accepted; non-matching errors are still flagged | Yes, at least one matching error | Test intentionally checks for a specific error |
| `satisfy(consumer)` | Consumer asserts on the list; all errors are treated as handled | Depends on assertions inside the consumer | Need to verify count or multiple error attributes |

You can remember them by intent:

- Want to ignore an optional error: use `filter`.
- Want to prove a specific error occurred: use `expect`.
- Want to inspect the entire list: use `satisfy`.

Do not use `satisfy` just to bypass error assertions. The consumer should explicitly verify the errors the test accepts.

## 9. Reading ResponseError to Write Accurate Predicates

The predicate receives a `ResponseError` object. This interface provides key details:

| Method | Meaning |
| --- | --- |
| `getMessage()` | Error description message |
| `getPath()` | String path of the failing field; returns an empty string if not tied to a field |
| `getParsedPath()` | Path as a list of segments, with field names as strings and list indices as integers |
| `getLocations()` | Locations in the GraphQL document if tied to a source location |
| `getErrorType()` | GraphQL Java error classification |
| `getExtensions()` | Additional metadata, possibly containing error codes or classification |

For example, a response error can be checked by path and code:

~~~java
import org.springframework.graphql.ResponseError;

private static boolean isRecommendationUnavailable(ResponseError error) {
    return "book.recommendation".equals(error.getPath())
            && "RECOMMENDATION_UNAVAILABLE".equals(
                    error.getExtensions().get("code"));
}
~~~

Using it in a test:

~~~java
graphQlTester.document(document)
        .execute()
        .errors()
        .expect(MyGraphQlErrorPredicates::isRecommendationUnavailable)
        .verify()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
~~~

Predicates can live in a helper class for reuse across tests. Keep helpers specific to error codes and field paths so readers know exactly which error is accepted.

## 10. Prefer path and extensions.code Over Comparing Only Messages

Messages are typically written for human readability and may change due to wording edits, localization, or exception formatting. Therefore, if the server exposes a stable error code in `extensions`, prefer matching that code.

Example of a sufficiently specific predicate:

~~~java
import org.springframework.graphql.ResponseError;

import java.util.function.Predicate;

private static Predicate<ResponseError> recommendationUnavailable() {
    return error ->
            "book.recommendation".equals(error.getPath())
                    && "RECOMMENDATION_UNAVAILABLE".equals(
                            error.getExtensions().get("code"));
}
~~~

Usage:

~~~java
.errors()
.expect(recommendationUnavailable())
.verify()
~~~

If checking only the message:

~~~java
.errors()
.filter(error -> error.getMessage().contains("unavailable"))
.verify()
~~~

the predicate might accidentally match an error from a different field or a new error with similar wording. This causes the test to silently overlook regressions.

Combine multiple properties to pinpoint the exact error:

- Path identifies the failing field.
- `extensions.code` identifies the business error category.
- Error classification can help distinguish broad error groups.
- Message should only be used when the message text itself is part of the contract under test.

## 11. Understanding Error Paths Correctly

`ResponseError.getPath()` returns the field path in the **response**, not a Java class path or resolver name. Paths can include list indices and client-chosen aliases.

Example query:

~~~graphql
query {
    book(id: "book-42") {
        suggested: recommendation {
            id
        }
    }
}
~~~

If the recommendation field fails, the path in the response might be:

~~~json
{
    "path": ["book", "suggested"]
}
~~~

Because the query uses the alias `suggested`, the predicate must compare against `book.suggested`, not `book.recommendation`.

For lists, the path may contain indices:

~~~json
{
    "path": ["books", 1, "author", "biography"]
}
~~~

`getPath()` formats this as a string, such as `books[1].author.biography`. When checking each segment without depending on string formatting, use `getParsedPath()`.

Not every GraphQL error has a path. Parse errors or certain request-level errors may not belong to a specific field; in that case, the path is empty. Do not use a predicate checking only a field path to filter request-level errors.

## 12. Using Error Classification and Extensions

Besides `extensions.code`, you can check the general error classification.

Example:

~~~java
import org.springframework.graphql.ResponseError;
import org.springframework.graphql.execution.ErrorType;

private static boolean isNotFoundAtBookField(ResponseError error) {
    return "book".equals(error.getPath())
            && ErrorType.NOT_FOUND.equals(error.getErrorType());
}
~~~

Classification distinguishes categories such as `NOT_FOUND`, `FORBIDDEN`, or `BAD_REQUEST`, depending on how the server constructs errors. Codes in `extensions.code` usually describe a more specific business case, such as `BOOK_NOT_FOUND` or `BOOK_VERSION_CONFLICT`.

Do not assume every server error has the same classification or custom code. Predicates must match the actual error contract published by the API.

Example response:

~~~json
{
    "errors": [
        {
            "message": "Book not found",
            "path": ["book"],
            "extensions": {
                "classification": "NOT_FOUND",
                "code": "BOOK_NOT_FOUND"
            }
        }
    ]
}
~~~

You can check both code and path to ensure the test accepts only the exact intended scenario:

~~~java
.errors()
.expect(error ->
        "book".equals(error.getPath())
                && "BOOK_NOT_FOUND".equals(
                        error.getExtensions().get("code")))
.verify()
~~~

## 13. Registering a Global errorFilter on the Builder

If a type of error is expected across many tests using the same tester, you can register the predicate directly on the builder using `errorFilter(...)`.

Example with `WebGraphQlTester`:

~~~java
import org.springframework.graphql.ResponseError;
import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.test.tester.WebGraphQlTester;

import java.util.function.Predicate;

Predicate<ResponseError> expectedRecommendationWarning =
        error -> "book.recommendation".equals(error.getPath())
                && "RECOMMENDATION_UNAVAILABLE".equals(
                        error.getExtensions().get("code"));

WebGraphQlTester graphQlTester =
        WebGraphQlTester.builder(handler)
                .errorFilter(expectedRecommendationWarning)
                .build();
~~~

A predicate registered on the builder applies to every request executed with that tester. You can configure this similarly on builders of other `GraphQlTester` types.

Afterward, tests do not need to re-declare the filter on each response:

~~~java
graphQlTester.document(document)
        .execute()
        .verify()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
~~~

Use global filters only when the exact same error is truly expected across all tests using that tester. If an error is only valid for one operation or scenario, put `errors().filter(...)` in that specific test to keep the scope tight.

Do not configure an overly broad predicate such as:

~~~java
.errorFilter(error -> true)
~~~

This causes every GraphQL error to be ignored across all requests on that tester, allowing tests to pass even when the API produces serious failures.

## 14. Combining filter and expect in the Same Response

You can chain multiple error-handling rules before calling `verify()`. For example, a query might have an optional ignorable warning while simultaneously requiring an authorization error on another field:

~~~java
graphQlTester.document("""
        query {
            dashboard {
                title
                recommendations {
                    id
                }
                privateNotes
            }
        }
        """)
        .execute()
        .errors()
        .filter(error ->
                "dashboard.recommendations".equals(error.getPath())
                        && "RECOMMENDATIONS_UNAVAILABLE".equals(
                                error.getExtensions().get("code")))
        .expect(error ->
                "dashboard.privateNotes".equals(error.getPath())
                        && "FORBIDDEN".equals(
                                error.getExtensions().get("code")))
        .verify()
        .path("dashboard.title")
        .entity(String.class)
        .isEqualTo("My dashboard");
~~~

Meaning:

- The recommendation error is ignored if present; filter does not require it to appear.
- The forbidden error must appear; if absent, `expect(...)` fails the test.
- Any other errors not matching these conditions are still caught by `verify()`.

When combining multiple predicates, name helpers after their business meaning and avoid duplicating long conditional expressions across tests.

## 15. Error Filter and executeAndVerify()

For mutations without response data to assert, `GraphQlTester` provides the `executeAndVerify()` helper to execute and verify the response has no GraphQL errors.

Example:

~~~java
graphQlTester.document("""
        mutation {
            archiveBook(id: "book-42")
        }
        """)
        .executeAndVerify();
~~~

`executeAndVerify()` is appropriate when the goal is confirming an operation completes without errors. If the test needs to accept or check a specific error, use `execute()` and declare `errors().filter(...)`, `errors().expect(...)`, or `errors().satisfy(...)`.

Do not use `executeAndVerify()` for a scenario intentionally returning a GraphQL error unless an appropriate error filter is configured, because this helper is designed to assert zero errors.

## 16. Common Errors When Using Error Filters

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Test still fails at `verify()` | Predicate does not match the actual error or another error remains | Check message, path, extensions, and the error list |
| Test passes even though error did not occur | Used `filter(...)` when needing to assert the error must exist | Switch to `expect(...)` |
| Test ignores too many errors | Predicate checks only a generic message or uses `error -> true` | Combine path with a specific error code |
| Filter does not apply when reading data path | Called `path(...)` before handling `errors()` | Handle errors before calling `path(...)` |
| Test fails to catch error at an alias | Predicate used schema field name instead of response alias | Check actual `getPath()` or `getParsedPath()` |
| `satisfy(...)` misses other errors | Consumer marked all errors as filtered while asserting only part of them | Verify the full error list and count |
| Global filter hides regressions | Builder applies predicate to every request | Configure only truly shared errors; prefer local filters |
| Filter fails to catch parse/coercion errors | Error has no field path or predicate targets only execution errors | Test request-level errors separately; avoid broad ignoring |
| Filter does not handle HTTP/network errors | Error filter only receives `ResponseError` from GraphQL responses | Check transport exceptions and HTTP status at the client layer |
| Message change breaks tests | Predicate depends on unstable wording | Prefer `extensions.code` and path |

## 17. Workflow for Choosing an Error Filter for a Test

When a response contains GraphQL errors, determine the test's objective first:

1. Decide whether the test needs to check data, a specific error, or the entire error list.
2. If no GraphQL errors are acceptable, use `execute()` and `errors().verify()` or `executeAndVerify()`.
3. If an error may appear and can be ignored, use `filter(predicate)`.
4. If the test must receive an error, use `expect(predicate)`.
5. If you need to inspect count, path, message, and extensions of all errors, use `satisfy(consumer)`.
6. Write predicates based on path and `extensions.code` when the API provides stable error codes.
7. Handle errors before navigating to `path(...)`.
8. Reserve global filters for truly common errors; use local filters for specific scenarios.
9. Verify that unexpected errors still fail the test.
10. Never use filters to mask server or transport bugs.

## 18. Key Takeaways

- Error filters are a response verification mechanism of `GraphQlTester`, not a server error handler.
- `errors().filter(...)` ignores errors matching the predicate without requiring them to appear.
- `errors().expect(...)` requires at least one matching error and still catches unexpected errors.
- `errors().satisfy(...)` lets you inspect the entire list and marks all errors as handled.
- `Builder.errorFilter(...)` applies a predicate to all requests made by that tester.
- `ResponseError` provides message, path, parsed path, locations, error type, and extensions.
- Prefer checking path together with `extensions.code` instead of relying only on message text.
- Paths use response aliases and list indices.
- Errors must be handled before asserting data paths.
- Overly broad predicates or uncontrolled global filters can hide regressions.

Error filters help write more accurate GraphQL tests when responses contain partial data or expected errors. Choosing properly among `filter`, `expect`, and `satisfy`, while scoping predicates by path and error code, allows tests to verify valid data while continuing to catch unexpected errors.

## References

- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [GraphQlTester.Errors API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/GraphQlTester.Errors.html)
- [ResponseError API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/ResponseError.html)
