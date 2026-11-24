# Spring GraphQL: Testing Data Paths, GraphQL Errors, and Nullability

## 1. Why must GraphQL tests check both data and errors?

In REST, a test typically starts with the HTTP status code and response body. With GraphQL, that is **not enough**: many errors raised **while executing a field** are still returned with HTTP 200, alongside **partial `data`** and an **`errors`** array. If a test only checks `status=200`, it can miss resolver failures, missing fields, or Non-Null constraint violations.

Example query:

~~~graphql
query {
  book(id: "B-1") {
    id
    title
    note
  }
  status
}
~~~

When everything succeeds, the response might look like:

~~~json
{
  "data": {
    "book": {
      "id": "B-1",
      "title": "Spring GraphQL",
      "note": "2026 Edition"
    },
    "status": "READY"
  }
}
~~~

If the resolver for `book.note` fails while `note` is a **nullable** field, GraphQL can return **partial data**:

~~~json
{
  "data": {
    "book": {
      "id": "B-1",
      "title": "Spring GraphQL",
      "note": null
    },
    "status": "READY"
  },
  "errors": [
    {
      "message": "Internal error",
      "locations": [{"line": 5, "column": 5}],
      "path": ["book", "note"]
    }
  ]
}
~~~

This is a **structural illustration**, without guaranteeing the exact error message or line/column numbers of a specific Spring GraphQL version. What forms the contract is the **error location**, which data survives, how `null` propagates according to the schema, and the business error codes defined by the application.

This lesson focuses on **testing Spring Boot applications using Spring for GraphQL** via `GraphQlTester` and live HTTP. SOAP is only briefly compared to avoid confusing GraphQL `errors.path` with XPath or SOAP Faults.

### Learning objectives

After this lesson, you will be able to:

1. Write assertions for nested fields, aliases, list indices, and objects decoded from `data`.
2. Distinguish **an omitted field**, **a valid null field value**, and **a field nulled due to an error**.
3. Read `errors.message`, `errors.locations`, `errors.path`, and `errors.extensions`; avoid writing tests coupled to internal messages.
4. Understand **Non-Null propagation/bubbling** for `T!`, `[T]`, `[T!]`, `[T]!`, and `[T!]!`.
5. Use `GraphQlTester.path(...)`, `valueIsNull()`, `pathDoesNotExist()`, `errors().expect(...)`, `errors().satisfy(...)`, and `errors().verify()`.
6. Write a Java 17+/Spring Boot 3.5.x example with `@GraphQlTest` and `@MockitoBean`, plus an HTTP integration test using JDK `HttpClient` to inspect raw JSON `data: null`.
7. Properly test request errors, execution errors, nullability, and partial data without equating them to HTTP 4xx/5xx.

## 2. Shape of a GraphQL response

A typical GraphQL response contains the following keys:

| Key | Meaning | Always present? |
| --- | --- | --- |
| `data` | Data of the executed operation | Present when the operation was executed; value may be `null` |
| `errors` | List of parse/validation/execution or field resolver errors | Present only when errors occurred; each error has `message` |
| Root-level `extensions` | Implementation-specific additional metadata | Optional |
| `errors[].path` | Path to the response field where an execution error occurred | Present for errors tied to a response position; request errors may omit it |
| `errors[].locations` | 1-based position in the query document | Present when a location can be identified |
| `errors[].extensions` | Error code/classification/custom metadata | Depends on implementation and application |

We must distinguish **two groups of GraphQL errors**:

**Request error:** invalid query syntax, field missing from schema, wrong argument type, invalid variable. The operation may be rejected **before execution**; the response contains `errors` but **no `data` key**.

**Execution error:** a field resolver fails, output cannot be coerced, or `null` is returned where the schema requires Non-Null. The operation was executed; the response contains `data`—either a **partial object** or **`null`**—along with `errors`. One field error does not necessarily discard the entire query result.

Do not hardcode "GraphQL error = HTTP 500." GraphQL-over-HTTP defines different status codes based on error kind, `Accept` media type, and implementation. For execution errors, HTTP 200 is common and valid. HTTP tests should assert the **GraphQL body** alongside the status per the transport contract.

### 2.1 Cases that look similar but have different meanings

~~~json
{"data":{"book":{"id":"B-1","note":null}}}
~~~

`note` was selected and **is null**, with **no errors**: this can be a valid null under the schema.

~~~json
{"data":{"book":{"id":"B-1"}}}
~~~

`note` **does not appear** because the operation did not request that field (or the response was unexpectedly altered). This is **not** `note: null`.

~~~json
{
  "data":{"book":{"id":"B-1","note":null}},
  "errors":[{"message":"...","path":["book","note"]}]
}
~~~

`note` is null **because of an execution error** (when the error is attached to that exact path). Looking at `data.book.note` alone cannot distinguish this from a valid null; you must check `errors`.

~~~json
{
  "data":{"book":null,"status":"READY"},
  "errors":[{"message":"...","path":["book","title"]}]
}
~~~

An error on `book.title` can turn **the entire `book` into null** if `title: String!`, even though the error still points to the deeper `title` field.

~~~json
{
  "data":null,
  "errors":[{"message":"...","path":["strictBook","title"]}]
}
~~~

If `strictBook: Book!` and `title: String!` fails, `null` can bubble all the way to **root `data`**. This is still an execution result, **unlike** a request validation response where the `data` key is absent.

## 3. Data path and error path are not the same thing

A **Data path** is how a test selects values inside `data`. With Spring `GraphQlTester`, `path("book.title")` starts from the **root of `data`**; do not write `path("data.book.title")`.

An **Error path** is an **array of segments** in `errors[*].path` per the GraphQL specification, for example:

~~~json
["books", 1, "title"]
~~~

- `"books"`: field name in the response.
- `1`: **0-based** index of the second element.
- `"title"`: child field name where the error occurred.

Spring's `ResponseError.getParsedPath()` returns a value equivalent to `List.of("books", 1, "title")`; `getPath()` is a string representation like `books[1].title`. **Do not confuse the integer `1` with the string `"1"`**.

### 3.1 Aliases change the error path

Operation:

~~~graphql
query {
  chosen: book(id: "B-1") {
    id
    title
  }
}
~~~

The response uses key `chosen` instead of `book`. If `title` fails, `errors[*].path` is:

~~~json
["chosen", "title"]
~~~

This is the path **in the response**, not the original schema field name or Java method name. Tests must assert the alias properly. When selecting data, use `path("chosen.id")`, not `path("book.id")`.

### 3.2 When an error bubbles, the error path stays deep

If `Book.title: String!` returns null and `Query.book: Book` is nullable, data becomes `{"book":null}`. Yet the error still records `["book","title"]`. It identifies the **origin** of the error, not the last surviving field in `data`.

Therefore, two assertions belong together:

1. `errors.path` identifies the exact failing field.
2. `data` shows the exact subtree nulled per the schema and which siblings remain intact.

Asserting only `book == null` does not prove why it is null; asserting only `errors.path` does not prove null propagation honors the contract.

## 4. Nullability in GraphQL SDL

GraphQL SDL uses `!` to denote a Non-Null type.

| SDL type | Can the list be null? | Can an item be null? | Valid examples |
| --- | --- | --- | --- |
| `Book` | Not a list; field can be null | — | `null` or a Book object |
| `Book!` | Not a list; field **cannot be null** | — | Valid Book; null causes execution error |
| `[Book]` | Yes | Yes | `null`, `[]`, `[book,null]` |
| `[Book!]` | Yes | No | `null`, `[]`, `[book]` |
| `[Book]!` | No | Yes | `[]`, `[book,null]` |
| `[Book!]!` | No | No | `[]` or a list of all valid Books |

**`!` is not Java `@NotNull` and does not prevent a Java method from returning null.** The GraphQL executor checks the resolved data and then applies coercion and null propagation.

Suppose the schema is:

~~~graphql
type Query {
  book(id: ID!): Book
  strictBook(id: ID!): Book!
  optionalBooks: [Book]
  books: [Book!]!
}

type Book {
  id: ID!
  title: String!
  note: String
}
~~~

Consequences when `title` is null:

- `book: Book` can become `null`, while nullable/valid root siblings still return data.
- `strictBook: Book!` causes the error to bubble from `Book.title` to `strictBook` and further to root `data: null`.
- `optionalBooks: [Book]` with a null title on the second item produces `optionalBooks: [validBook, null]`; the list remains intact.
- `books: [Book!]!` with one broken item turns the entire list null, then bubbles to root data because the list itself is Non-Null.
- `[Book!]` (nullable list, Non-Null item) turns the **entire list null**, while still keeping root siblings.
- `[Book]!` (Non-Null list, nullable item) preserves the list and replaces only the failing item with null.

### 4.1 Why does null bubble up to the parent?

Mandatory rule: a field declared Non-Null **cannot** receive null in successful data. When a resolver returns null or errors on a Non-Null field, GraphQL treats it as an execution error and assigns **null to the parent response position**. If the parent is also Non-Null, bubbling continues upward until it hits a nullable field or root data.

Example:

~~~text
Query.book: Book          (nullable)
    |
    +-- Book.id: ID!      = "B-1"
    |
    +-- Book.title:String! = null  <-- Non-Null violation
             |
             v
Query.book becomes null           <-- stopping point
Query.status remains "READY"      <-- root sibling can still survive
errors.path = ["book","title"]     <-- error still points to original field
~~~

**One error, not necessarily a new error at every bubbled level.** Null propagation to the parent does not mean adding a new error entry for every ancestor. Tests should not expect the errors array to contain `book.title`, `book`, and `data` for the same violation.

### 4.2 Null of an object vs. null of a list element

With `optionalBooks: [Book]`:

~~~json
{
  "data": {
    "optionalBooks": [
      {"id":"B-1","title":"Spring GraphQL"},
      null
    ]
  },
  "errors": [
    {"message":"...","path":["optionalBooks",1,"title"]}
  ]
}
~~~

The element with a broken `title` becomes null, while its index is preserved. Failing elements are not automatically filtered out nor are later elements shifted to index 1. That is why `errors.path` includes the list index.

### 4.3 An empty list is not null

`[]` is a **valid list with zero elements** and can appear in any list type above, including `[Book!]!`. It differs from `null`. `GraphQlTester.path(...).hasValue()` means non-null **or non-empty list**; therefore, when expecting an empty list, use `entityList(...).hasSize(0)` instead of `hasValue()`.

## 5. GraphQlTester: DSL for data paths

Spring for GraphQL ships the `spring-graphql-test` artifact, providing transport-independent `GraphQlTester`. A test selects an operation via `document(...)`, optionally binds variables, calls `execute()`, and then asserts.

~~~java
GraphQlTester.Response response = tester.document("""
        query BookById($id: ID!) {
          book(id: $id) {
            id
            title
            note
          }
        }
        """)
        .variable("id", "B-1")
        .execute();

response.path("book.id")
        .entity(String.class)
        .isEqualTo("B-1");

response.path("book.title").hasValue();
~~~

This is an **excerpt inside a test that has `GraphQlTester tester` and imports**, not a standalone file. `GraphQlTester.Response` is the object returned by `execute()`; it lets you inspect multiple paths on the **same response** instead of re-running the query multiple times.

### 5.1 Essential assertions

| Method | Meaning | Use case |
| --- | --- | --- |
| `path("book.title").entity(String.class).isEqualTo("...")` | Decode scalar and compare exactly | Required string field |
| `path("book").hasValue()` | Field exists with non-null value or non-empty list | Object expected to be present |
| `path("book.note").valueIsNull()` | Field exists with JSON null value | Nullable note absent |
| `path("book.note").pathDoesNotExist()` | Path absent from `data` | Query omitted note |
| `path("books").entityList(BookView.class).hasSize(2)` | Decode list and verify item count | Bounded list |
| `path("book").entity(BookView.class).isEqualTo(expected)` | Decode object and compare data | DTO/record with equals |
| `path("book").matchesJson("{...}")` | Compare JSON structure | Multiple stable fields |

**Spring GraphQL 1.x method names to spell accurately:** `valueIsNull()` and `pathDoesNotExist()`, **not** `isNull()` / `doesNotExist()`. This is a common discrepancy when learning from milestone examples or other DSLs.

### 5.2 Data paths do not start with data

Given response:

~~~json
{"data":{"book":{"id":"B-1"}}}
~~~

Correct:

~~~java
response.path("book.id").entity(String.class).isEqualTo("B-1");
~~~

Incorrect scope:

~~~java
// Do not prepend "data." when calling GraphQlTester.path(...).
response.path("data.book.id");
~~~

`GraphQlTester` already roots paths at `data`. The `errors` section is inspected via `response.errors()`, not via `path("errors[0].path")` as if errors were a data field.

### 5.3 Array paths and aliases

If the schema/query returns `books` as an array:

~~~java
response.path("books[0].title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

If the query uses an alias `chosen: book(...)`:

~~~java
response.path("chosen.id")
        .entity(String.class)
        .isEqualTo("B-1");
~~~

JSONPath supports expressions such as `books[*].id`; when asserting lists, use `entityList(...)` or appropriate assertions. Do not hardcode indices from a query with unspecified ordering; when stable positions matter, define an ordering contract.

## 6. GraphQlTester: DSL for errors

By default, calling `path(...)` on a response with **unhandled/unchecked GraphQL errors** causes `GraphQlTester` to fail. This is a helpful safeguard: a happy-path test should not accidentally PASS when the query returns partial data accompanied by errors.

### 6.1 Expecting no errors: verify zero errors

~~~java
GraphQlTester.Response response = tester.document("""
        query { book(id: "B-1") { id title } }
        """).execute();

response.errors().verify();
response.path("book.id").entity(String.class).isEqualTo("B-1");
~~~

`errors().verify()` asserts there are no unexpected GraphQL errors. If the operation returns no errors, going directly to `response.path(...)` also performs the default error check, though calling `verify()` explicitly makes the intent clear.

### 6.2 Expecting a single error by path

~~~java
GraphQlTester.Traversable data = tester.document("""
        query {
          book(id: "BROKEN-NOTE") { id title note }
          status
        }
        """)
        .execute()
        .errors()
        .expect(error -> error.getPath().equals("book.note"))
        .verify();

data.path("book.id")
        .entity(String.class)
        .isEqualTo("BROKEN-NOTE");
data.path("book.note").valueIsNull();
data.path("status").entity(String.class).isEqualTo("READY");
~~~

`expect(predicate)` differs from `filter(predicate)`:

- `expect` requires **at least one matching error to exist**, otherwise it fails; expected errors no longer block subsequent data assertions.
- `filter` merely ignores matching errors if present and **does not require** an error to occur. Using `filter` to test a mandatory error branch is wrong.
- `verify` fails if any unexpected errors remain unhandled.
- To check **exact error count, path, message/code, and metadata**, use `satisfy(...)` and assert the contents of the list.

### 6.3 Asserting the exact errors array, including list indices

~~~java
GraphQlTester.Traversable data = tester.document("""
        query {
          optionalBooks { id title }
          status
        }
        """)
        .execute()
        .errors()
        .satisfy(errors -> {
            assertEquals(1, errors.size());
            assertEquals(
                    List.of("optionalBooks", 1, "title"),
                    errors.get(0).getParsedPath());
        });

data.path("optionalBooks[1]").valueIsNull();
data.path("status").entity(String.class).isEqualTo("READY");
~~~

This snippet requires `java.util.List` and `assertEquals` in the test. `satisfy` exposes the **entire** errors list and treats them as handled; therefore, **be sure to assert the count and contents** inside the lambda. Writing an empty `satisfy(errors -> {})` can silently ignore any unexpected errors.

### 6.4 Do not depend on internal error messages

GraphQL Java/Spring GraphQL may mask unhandled exceptions as messages like "Internal error..." with an execution ID. Specific error wording, error classification for unhandled exceptions, locations, and formatting can vary across versions.

Prefer asserting:

1. Exact `getParsedPath()` or `getPath()`.
2. Expected error count when defined by the contract.
3. `extensions.code` **only if your API defines stable codes**, not arbitrary internal framework enums/strings.
4. No raw stack traces, SQL queries, or tokens leaked in `message`/`extensions`.

If the application defines a `DataFetcherExceptionResolver` or `@GraphQlExceptionHandler` mapping domain errors to a code like `BOOK_NOT_FOUND`, also assert `errors[].extensions.code` via `getExtensions()`. Keep valid "null because record does not exist" distinct from "unhandled exception" so API semantics remain consistent.

## 7. A small schema to test both nullable and Non-Null

In the hands-on project, the SDL in `src/main/resources/graphql/schema.graphqls` is:

~~~graphql
type Query {
  book(id: ID!): Book
  strictBook(id: ID!): Book!
  books: [Book!]!
  optionalBooks: [Book]
  status: String!
}

type Book {
  id: ID!
  title: String!
  note: String
}
~~~

This is the **complete schema** for the example, with no mutations or subscriptions. Intentional design:

- `book` nullable → allows not finding a book without raising an error.
- `strictBook` Non-Null → if no book exists or a Non-Null child fails, can produce `data: null`.
- `books` Non-Null list and Non-Null item → a single item failure bubbles through the list to root.
- `optionalBooks` nullable list and item → one item failing does not invalidate the list.
- `title` Non-Null → lets us trigger required bubbling when its getter returns null.
- `note` nullable → allows natural null or null from a failing resolver while keeping other fields.
- `status` Non-Null sibling returning `READY` → demonstrates partial data preserving siblings when an error stops at a nullable field.

In a production API, schema nullability is a **contract with clients**. Changing `Book` to `Book!` or `[Book]` to `[Book!]!` is a change that can severely break clients when bad data or infrastructure errors occur.

## 8. Runnable Java 17+ / Spring Boot 3.5.x example

The hands-on lab includes production files, GraphQL SDL, and two test classes:

- **`@GraphQlTest`**: tests data paths/errors/nullability directly on the GraphQL execution engine **without starting an HTTP server**, with the catalog mocked via Mockito.
- **`@SpringBootTest(RANDOM_PORT)`**: tests raw JSON over **live HTTP** to verify `data:null` presence, error paths with list indices, and sibling survival.

No database, Kafka, Redis, Docker, or external services are used. The live test uses **JDK `java.net.http.HttpClient`** instead of WebClient to inspect the raw JSON wire format directly without needing a separate GraphQL HTTP test transport.

### 8.1 Directory tree

~~~text
src/
  main/
    java/
      example/graphqltest/
        GraphQlDemoApplication.java
        Book.java
        BookCatalog.java
        InMemoryBookCatalog.java
        BookGraphQlController.java
    resources/
      graphql/
        schema.graphqls
  test/
    java/
      example/graphqltest/
        BookGraphQlSliceTest.java
        BookGraphQlHttpTest.java
~~~

All Java sources use package `example.graphqltest`. Place tests in or below the primary `@SpringBootApplication` package so Spring Boot locates the root configuration. Java 17 supports text blocks for GraphQL documents.

### 8.2 GraphQlDemoApplication.java

~~~java
package example.graphqltest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GraphQlDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(GraphQlDemoApplication.class, args);
    }
}
~~~

Boot component-scans the controller and production catalog, and initializes the GraphQL schema from `classpath:graphql/**/` under Spring Boot's defaults.

### 8.3 Book.java — POJO with explicit getters

~~~java
package example.graphqltest;

public final class Book {
    private final String id;
    private final String title;
    private final String note;

    public Book(String id, String title, String note) {
        this.id = id;
        this.title = title;
        this.note = note;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getNote() {
        return note;
    }
}
~~~

JavaBean getters let `graphql-java PropertyDataFetcher` resolve `Book.id` and `Book.title` cleanly. The `note` field also has a getter, though the controller declares an explicit `@SchemaMapping` for it to simulate a resolver failure.

**Important:** allowing `title == null` in the constructor is **intentional for testing Non-Null errors**. Do not treat this as a production domain design recommendation; normally, validate invariants early so data cannot violate the GraphQL schema.

### 8.4 BookCatalog.java — dependency interface

~~~java
package example.graphqltest;

import java.util.List;

public interface BookCatalog {
    Book findById(String id);
    List<Book> findAll();
}
~~~

The interface does not return reactive types because the example focuses on **GraphQL execution semantics**, not `Mono`/`Flux`. Spring GraphQL still supports synchronous resolver return values; a real application may use `Mono<Book>`/`Flux<Book>` and test equivalently.

### 8.5 InMemoryBookCatalog.java — fixed fixture data

~~~java
package example.graphqltest;

import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class InMemoryBookCatalog implements BookCatalog {

    @Override
    public Book findById(String id) {
        return switch (id) {
            case "B-1" ->
                    new Book("B-1", "Spring GraphQL", "2026 Edition");
            case "NO-NOTE" ->
                    new Book("NO-NOTE", "Optional Field", null);
            case "BROKEN-NOTE" ->
                    new Book("BROKEN-NOTE", "Readable Title", "ignored");
            case "BAD-TITLE" ->
                    new Book("BAD-TITLE", null, "Note still exists");
            default -> null;
        };
    }

    @Override
    public List<Book> findAll() {
        return List.of(
                findById("B-1"),
                findById("BAD-TITLE"));
    }
}
~~~

Fixture explanation:

- `B-1`: all fields valid.
- `NO-NOTE`: `note == null` is a normal nullable value, **no error**.
- `BROKEN-NOTE`: the controller throws an exception in `@SchemaMapping` for `note`; even though the Book object holds a note string, the dedicated GraphQL data fetcher governs that field.
- `BAD-TITLE`: `getTitle()` returns null, intentionally violating `Book.title: String!` and triggering Non-Null propagation.
- `findAll()`: two items, with the second having a null title to test list index errors.

All data is an in-memory fixture with stable ordering. No external database or network calls exist.

### 8.6 BookGraphQlController.java — real resolvers

~~~java
package example.graphqltest;

import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookGraphQlController {
    private final BookCatalog catalog;

    public BookGraphQlController(BookCatalog catalog) {
        this.catalog = catalog;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return catalog.findById(id);
    }

    @QueryMapping
    public Book strictBook(@Argument String id) {
        return catalog.findById(id);
    }

    @QueryMapping
    public List<Book> books() {
        return catalog.findAll();
    }

    @QueryMapping
    public List<Book> optionalBooks() {
        return catalog.findAll();
    }

    @QueryMapping
    public String status() {
        return "READY";
    }

    @SchemaMapping(typeName = "Book", field = "note")
    public String note(Book book) {
        if ("BROKEN-NOTE".equals(book.getId())) {
            throw new IllegalStateException("note provider unavailable");
        }
        return book.getNote();
    }
}
~~~

`@QueryMapping` binds methods to fields on the `Query` type by method name. `@SchemaMapping(typeName="Book", field="note")` defines a dedicated resolver for `Book.note`; `id` and `title` are fetched by graphql-java from the POJO getters.

For `BROKEN-NOTE`, the exception in `note` is a **field-level execution error**. Spring GraphQL/GraphQL Java may sanitize the error message to avoid exposing implementation details. The test **does not assert the original exception message**, checking only the path and partial data.

For `BAD-TITLE`, the controller throws no exception: **GraphQL output coercion/Non-Null rules** detect `getTitle() == null` and propagate the error. These are two distinct error sources, very helpful for learning to tell them apart.

### 8.7 Slice test — BookGraphQlSliceTest.java

~~~java
package example.graphqltest;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.when;

@GraphQlTest(BookGraphQlController.class)
@DisplayName("GraphQlTester data path, errors, nullability")
class BookGraphQlSliceTest {

    @Autowired
    GraphQlTester tester;

    @MockitoBean
    BookCatalog catalog;

    private static Book good() {
        return new Book("B-1", "Spring GraphQL", "2026 Edition");
    }

    private static Book badTitle() {
        return new Book("BAD-TITLE", null, "Note still exists");
    }

    @Test
    @DisplayName("Query variable, nested data paths, and scalar decode")
    void readsNestedDataPaths() {
        when(catalog.findById("B-1")).thenReturn(good());

        GraphQlTester.Response response = tester.document("""
                query BookById($id: ID!) {
                  book(id: $id) { id title note }
                }
                """)
                .variable("id", "B-1")
                .execute();

        response.errors().verify();
        response.path("book").hasValue();
        response.path("book.id")
                .entity(String.class).isEqualTo("B-1");
        response.path("book.title")
                .entity(String.class).isEqualTo("Spring GraphQL");
        response.path("book.note")
                .entity(String.class).isEqualTo("2026 Edition");
    }

    @Test
    @DisplayName("Selected field with valid null produces no error")
    void acceptsNullableFieldWithoutError() {
        when(catalog.findById("NO-NOTE")).thenReturn(
                new Book("NO-NOTE", "Optional Field", null));

        GraphQlTester.Response response = tester.document("""
                { book(id: "NO-NOTE") { id note } }
                """).execute();

        response.errors().verify();
        response.path("book.id")
                .entity(String.class).isEqualTo("NO-NOTE");
        response.path("book.note").valueIsNull();
    }

    @Test
    @DisplayName("Unselected field differs from null field")
    void distinguishesOmittedField() {
        when(catalog.findById("B-1")).thenReturn(good());

        GraphQlTester.Response response = tester.document("""
                { book(id: "B-1") { id } }
                """).execute();

        response.errors().verify();
        response.path("book.id")
                .entity(String.class).isEqualTo("B-1");
        response.path("book.note").pathDoesNotExist();
    }

    @Test
    @DisplayName("Not-found nullable query field is a valid null")
    void missingNullableBookIsNotAnError() {
        when(catalog.findById("MISSING")).thenReturn(null);

        GraphQlTester.Response response = tester.document("""
                { book(id: "MISSING") { id title } status }
                """).execute();

        response.errors().verify();
        response.path("book").valueIsNull();
        response.path("status")
                .entity(String.class).isEqualTo("READY");
    }

    @Test
    @DisplayName("Exception on nullable field produces partial data and error path")
    void nullableResolverFailureKeepsSiblingData() {
        when(catalog.findById("BROKEN-NOTE")).thenReturn(
                new Book("BROKEN-NOTE", "Readable Title", "ignored"));

        GraphQlTester.Traversable data = tester.document("""
                {
                  book(id: "BROKEN-NOTE") { id title note }
                  status
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> {
                    assertEquals(1, errors.size());
                    assertEquals(
                            List.of("book", "note"),
                            errors.get(0).getParsedPath());
                    assertFalse(errors.get(0).getMessage().isBlank());
                });

        data.path("book.id")
                .entity(String.class).isEqualTo("BROKEN-NOTE");
        data.path("book.title")
                .entity(String.class).isEqualTo("Readable Title");
        data.path("book.note").valueIsNull();
        data.path("status")
                .entity(String.class).isEqualTo("READY");
    }

    @Test
    @DisplayName("Invalid Non-Null title makes book null while status remains")
    void nonNullChildBubblesToNullableParent() {
        when(catalog.findById("BAD-TITLE")).thenReturn(badTitle());

        GraphQlTester.Traversable data = tester.document("""
                {
                  book(id: "BAD-TITLE") { id title }
                  status
                }
                """)
                .execute()
                .errors()
                .expect(error ->
                        error.getParsedPath().equals(
                                List.of("book", "title")))
                .verify();

        data.path("book").valueIsNull();
        data.path("status")
                .entity(String.class).isEqualTo("READY");
    }

    @Test
    @DisplayName("List with nullable items preserves failing index")
    void nullableListElementBecomesNull() {
        when(catalog.findAll()).thenReturn(
                List.of(good(), badTitle()));

        GraphQlTester.Traversable data = tester.document("""
                {
                  optionalBooks { id title }
                  status
                }
                """)
                .execute()
                .errors()
                .expect(error ->
                        error.getParsedPath().equals(
                                List.of("optionalBooks", 1, "title")))
                .verify();

        data.path("optionalBooks[0].title")
                .entity(String.class).isEqualTo("Spring GraphQL");
        data.path("optionalBooks[1]").valueIsNull();
        data.path("status")
                .entity(String.class).isEqualTo("READY");
    }

    @Test
    @DisplayName("Alias becomes the actual name in errors.path")
    void errorPathUsesResponseAlias() {
        when(catalog.findById("BAD-TITLE")).thenReturn(badTitle());

        GraphQlTester.Traversable data = tester.document("""
                {
                  selected: book(id: "BAD-TITLE") { id title }
                }
                """)
                .execute()
                .errors()
                .expect(error ->
                        error.getPath().equals("selected.title"))
                .verify();

        data.path("selected").valueIsNull();
    }

    @Test
    @DisplayName("Empty list is valid even though hasValue does not fit")
    void verifiesEmptyListExplicitly() {
        when(catalog.findAll()).thenReturn(List.of());

        GraphQlTester.Response response = tester.document("""
                { optionalBooks { id title } }
                """).execute();

        response.errors().verify();
        response.path("optionalBooks")
                .entityList(Map.class).hasSize(0);
    }

    @Test
    @DisplayName("Unknown schema field is a request validation error")
    void invalidFieldIsARequestError() {
        tester.document("""
                { book(id: "B-1") { fieldNotInSchema } }
                """)
                .execute()
                .errors()
                .expect(error -> error.getParsedPath().isEmpty())
                .verify();
    }
}
~~~

**There are 10 JUnit Jupiter `@Test` methods.** The slice test does not start an HTTP server and needs no database; `@MockitoBean` injects a mock `BookCatalog` into the Spring test context, while the resolver, schema, nullability, GraphQL engine, and `GraphQlTester` are **real**.

### 8.8 Evidence analysis of each slice test

| Test | Key assertion | What it proves |
| --- | --- | --- |
| `readsNestedDataPaths` | Variable ID, `book.id/title/note` | GraphQL resolver + response paths + scalar decoding |
| `acceptsNullableFieldWithoutError` | `note.valueIsNull()` and `errors().verify()` | Valid null, not an execution failure |
| `distinguishesOmittedField` | `pathDoesNotExist()` | Unqueried field differs from null field |
| `missingNullableBookIsNotAnError` | `book == null`, sibling status intact | Nullable root field can be absent without error |
| `nullableResolverFailureKeepsSiblingData` | Error path `book.note`, note null, id/title/status intact | Partial data with resolver exception on nullable field |
| `nonNullChildBubblesToNullableParent` | Error path `book.title`, book null, status intact | Non-Null child nulls nullable parent |
| `nullableListElementBecomesNull` | Error path includes index `1`, item 1 null | `[Book]` preserves failing position without nulling the list |
| `errorPathUsesResponseAlias` | `selected.title` instead of `book.title` | Error path uses the response alias name |
| `verifiesEmptyListExplicitly` | `entityList(...).hasSize(0)` | Empty list differs from null; do not misuse `hasValue()` |
| `invalidFieldIsARequestError` | Error has no response field path | Pre-execution validation error, no resolver result |

**What must not be inferred:**

- Because the catalog is mocked, the test does not verify persistence or production SQL mapping.
- `invalidFieldIsARequestError` does not assert an HTTP status because it runs inside a GraphQL execution test **without HTTP transport**.
- `nullableResolverFailureKeepsSiblingData` does not depend on internal error wording; `satisfy` asserts count, parsed path, and non-blank message.
- `entityList(Map.class).hasSize(0)` checks emptiness only, avoiding object-mapper construction of a `Book` from an empty array.
- Every test stubs the collaborator inside its own method, avoiding execution-order or Mockito state coupling across test methods.

## 9. HTTP integration test: inspecting exact data:null and path indices

Some states require checking the **raw GraphQL response** instead of only asserting a data path. In particular:

- `data:null` is a **present key** whose value is null, not an object containing a null field.
- Request errors can cause the `data` key to be **absent**.
- Error paths are JSON arrays mixing strings and integers.
- HTTP status is a transport concern, **separate from** the count of GraphQL execution errors.

In the example, `@SpringBootTest(webEnvironment = RANDOM_PORT)` starts a real server, and JDK `HttpClient` sends JSON POST requests to `/graphql`. Spring for GraphQL's default endpoint on Spring Boot MVC is `/graphql`; if a project sets a different `spring.graphql.http.path`, adjust the URL accordingly.

### 9.1 BookGraphQlHttpTest.java

~~~java
package example.graphqltest;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@DisplayName("Real GraphQL HTTP: data null, errors.path")
class BookGraphQlHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    @Test
    @DisplayName("Non-Null root turns data into JSON null")
    void strictRootBubblesErrorToDataNull() throws Exception {
        JsonNode body = execute("""
                {
                  strictBook(id: "BAD-TITLE") { id title }
                  status
                }
                """);

        assertTrue(body.has("data"));
        assertTrue(body.get("data").isNull());
        assertEquals(1, body.path("errors").size());
        assertEquals("strictBook",
                body.path("errors").get(0)
                        .path("path").get(0).asText());
        assertEquals("title",
                body.path("errors").get(0)
                        .path("path").get(1).asText());
    }

    @Test
    @DisplayName("[Book!]! makes data null when second element fails")
    void strictListBubblesErrorToDataNull() throws Exception {
        JsonNode body = execute("""
                {
                  books { id title }
                  status
                }
                """);

        assertTrue(body.has("data"));
        assertTrue(body.get("data").isNull());

        JsonNode errors = body.path("errors");
        assertEquals(1, errors.size());

        JsonNode path = errors.get(0).path("path");
        assertEquals("books", path.get(0).asText());
        assertEquals(1, path.get(1).asInt());
        assertEquals("title", path.get(2).asText());
    }

    @Test
    @DisplayName("[Book] keeps siblings and nulls only the failing item")
    void nullableListKeepsPartialData() throws Exception {
        JsonNode body = execute("""
                {
                  optionalBooks { id title }
                  status
                }
                """);

        assertTrue(body.path("data").isObject());
        assertEquals("READY",
                body.path("data").path("status").asText());

        JsonNode books = body.path("data").path("optionalBooks");
        assertTrue(books.isArray());
        assertEquals(2, books.size());
        assertEquals("B-1", books.get(0).path("id").asText());
        assertTrue(books.get(1).isNull());

        JsonNode errors = body.path("errors");
        assertEquals(1, errors.size());
        JsonNode path = errors.get(0).path("path");
        assertEquals("optionalBooks", path.get(0).asText());
        assertEquals(1, path.get(1).asInt());
        assertEquals("title", path.get(2).asText());
    }

    @Test
    @DisplayName("HTTP happy path has data and no errors")
    void successReturnsNestedDataWithoutErrors() throws Exception {
        JsonNode body = execute("""
                {
                  selected: book(id: "B-1") { id title }
                  status
                }
                """);

        assertTrue(body.path("data").isObject());
        assertEquals("B-1",
                body.path("data").path("selected")
                        .path("id").asText());
        assertEquals("Spring GraphQL",
                body.path("data").path("selected")
                        .path("title").asText());
        assertEquals("READY",
                body.path("data").path("status").asText());
        assertFalse(body.has("errors"));
    }

    private JsonNode execute(String document) throws Exception {
        String requestJson = mapper.writeValueAsString(
                Map.of("query", document));

        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:"
                                + port + "/graphql"))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .timeout(Duration.ofSeconds(20))
                .POST(HttpRequest.BodyPublishers.ofString(
                        requestJson, StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> response = http.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        // All queries in this class are executed;
        // internal execution errors typically return HTTP 200.
        assertEquals(200, response.statusCode());

        return mapper.readTree(response.body());
    }
}
~~~

**There are 4 JUnit Jupiter `@Test` methods.** The tests do not depend on the execution order of GraphQL root fields, nor do they assert error messages containing execution IDs or exception text. They check exact **`data` keys**, null types, array items, aliases, and `errors.path`.

### 9.2 Why inspect raw JSON instead of only using GraphQlTester?

`GraphQlTester` is the best choice for most data and error assertions. However, when an error bubbles up to **root `data: null`**, inspecting the raw JSON response can be clearer than navigating a data path that no longer exists.

Over real HTTP, we simultaneously verify:

- Client encodes the GraphQL request as JSON.
- The `/graphql` endpoint accepts POST.
- GraphQL execution emits the right error path.
- Server encodes JSON with `data:null` or partial data.
- HTTP status matches the project's setup (here `Accept: application/json` and execution errors expect HTTP 200).

**Does not prove** databases, production authorization, network proxies, or WebSocket subscriptions, since the example uses none of them.

## 10. Distinguishing GraphQL execution errors from request validation errors in raw JSON

Example invalid query:

~~~graphql
query {
  book(id: "B-1") {
    fieldNotInSchema
  }
}
~~~

Per the specification, this is a **request error**: the validator detects an unknown field, **never runs the `book` resolver**, and returns no `data`.

An illustrative response:

~~~json
{
  "errors": [
    {
      "message": "Validation error...",
      "locations": [{"line": 3, "column": 5}]
    }
  ]
}
~~~

Absence of `data` is completely different from:

~~~json
{
  "data": null,
  "errors": [
    {
      "message": "...",
      "path": ["strictBook", "title"]
    }
  ]
}
~~~

At the transport layer, **the HTTP status for request errors should not be hardcoded to one universal rule**. When using media type `application/graphql-response+json` under GraphQL-over-HTTP, unexecuted request errors can lead to HTTP 400; with `application/json`, different implementations/versions may behave differently for compatibility. Test against your project's **transport contract**, and verify nullability using real execution responses.

### 10.1 A helper check for whether data is present

Java pattern in an HTTP test with `JsonNode body`:

~~~java
// Request error: no "data" entry at root.
assertFalse(body.has("data"));
assertTrue(body.path("errors").isArray());

// Bubbled execution error: "data" key is present and JSON null.
assertTrue(body.has("data"));
assertTrue(body.get("data").isNull());

// Nullable field: data object contains field with JSON null.
assertTrue(body.path("data").path("book").isNull());
~~~

These are **three patterns for three distinct responses**, not three assertions applied to the same `body`. Jackson's `path(...)` returns `MissingNode` when a key is absent; `get(...)` returns a Java null reference when absent. Combine `has("data")` with `get("data").isNull()` to distinguish **missing** from **JSON null**.

### 10.2 When an operation selects multiple root fields

A GraphQL query can select:

~~~graphql
query {
  book(id: "BAD-TITLE") { id title }
  status
}
~~~

`book` is nullable while child `title` is Non-Null, so `data.book = null`; `data.status = "READY"` can still appear. Conversely, using `strictBook: Book!` with a failing child title sets `data: null`, discarding sibling data from the payload even if the sibling resolver already ran.

**Do not infer "if the sibling is absent, its resolver definitely did not run."** GraphQL can start resolving fields before discovering null bubbling; tests should assert the **response contract** rather than internal scheduling.

## 11. Running the example with Gradle

In a Spring Boot **3.5.x** project already configured with the proper plugins, dependency management, and Java 17+ toolchain, the minimal dependencies in `build.gradle` are:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.graphql:spring-graphql-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is an **additional configuration snippet**, not a complete `build.gradle` with plugins, versions, and toolchain. The Spring Boot BOM must manage the matching `spring-graphql-test` version; avoid declaring an incompatible GraphQL Java version.

**Why not add `spring-boot-starter-webflux` here?** The slice test uses in-process `GraphQlTester` and the HTTP test uses **JDK `HttpClient`**, not `HttpGraphQlTester` which builds on a WebFlux client. If you want Spring's `HttpGraphQlTester` in HTTP tests, Boot docs specify adding `spring-graphql-test` and WebFlux test dependencies if not already present.

Run both classes:

~~~bash
./gradlew test --tests example.graphqltest.BookGraphQlSliceTest --tests example.graphqltest.BookGraphQlHttpTest
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.graphqltest.BookGraphQlSliceTest --tests example.graphqltest.BookGraphQlHttpTest
~~~

**Expected outcome:** **14 `@Test` methods** (10 slice + 4 HTTP integration) discovered by JUnit Jupiter and **PASS** in a Boot 3.5.x environment configured as described. Tests do not print stdout on their own; Gradle reports `BUILD SUCCESSFUL` and saves test reports in `build/reports/tests/test/index.html`. This is the **expected outcome from the design**, not a log of a verified build run.

If the project uses Spring Boot 4.x, some test helper packages, modules, and starter configurations change. Consult the migration guide and API for your exact version; the `@GraphQlTest` import here is written **specifically for Boot 3.5.x**.

## 12. Data paths: data types, nested objects, lists, and aliases

A GraphQL response can return a deeply nested graph, such as:

~~~graphql
query {
  viewer {
    id
    orders {
      id
      lines {
        sku
        quantity
      }
    }
  }
}
~~~

The data path to a line item can be:

~~~text
viewer.orders[0].lines[2].sku
~~~

With `GraphQlTester`:

~~~java
tester.document(document)
        .execute()
        .path("viewer.orders[0].lines[2].sku")
        .entity(String.class)
        .isEqualTo("BOOK-1");
~~~

This is an **illustrative pattern**, requiring a matching schema and `document`; it is not an endpoint in the sample project. The path starts at **`data.viewer`**.

When an operation returns an unsorted list, do not assert that `orders[0]` is a specific order. Require stable sorting in the schema/resolver or decode the list and look up by ID. If the contract does not guarantee ordering, index-dependent tests become flaky even when the service is correct.

### 12.1 Decoding objects by type instead of many JSONPath assertions

You can use a Java record:

~~~java
public record BookView(String id, String title, String note) {
}
~~~

In a test:

~~~java
BookView book = tester.document("""
        { book(id: "B-1") { id title note } }
        """)
        .execute()
        .path("book")
        .entity(BookView.class)
        .get();

assertEquals("B-1", book.id());
~~~

This is an **extended illustrative snippet**, requiring `BookView`, imports, and a mocked service returning a book. When your version of `GraphQlTester.Entity` supports `get()` (Spring GraphQL 1.x does), decoding an object can be cleaner than asserting many separate paths. For nullable fields or bubbled parents, **check errors and null first** instead of forcing deserialization of a non-existent object.

**Do not rely solely on direct JSON deserialization to verify absence of errors.** An object may decode cleanly while `errors` exist on a sibling field; `GraphQlTester` helps catch unexpected errors by default.

### 12.2 GraphQL null vs. Java Optional

An empty `Optional<Book>` or `Mono<Book>` in the backend can map to a nullable GraphQL `null`, which **does not automatically generate a GraphQL error**. To let clients distinguish "not found" from "upstream failed," establish an explicit schema/domain error policy.

Similarly, an `@Argument` receiving `ID!` is rejected by GraphQL input validation when the client passes null or omits the required argument; there is no need to wait for the Java controller to catch it. In tests, a request missing a required variable is a **request error**, not output Non-Null bubbling.

## 13. Checking multiple GraphQL errors without relying on order

A query can return multiple execution errors, such as two independent nullable root fields failing together. GraphQL does not require applications to keep a deterministic **errors array ordering** based on resolver completion order, especially under concurrency or batching.

Instead of:

~~~java
// Brittle if error ordering changes:
assertEquals("first.title", errors.get(0).getPath());
assertEquals("second.note", errors.get(1).getPath());
~~~

Assert the **set of error paths** when the contract only guarantees set membership:

~~~java
Set<String> paths = errors.stream()
        .map(error -> error.getPath())
        .collect(Collectors.toSet());

assertEquals(
        Set.of("first.title", "second.note"),
        paths);
~~~

This is a **pattern inside an `errors().satisfy(errors -> {...})` lambda**; import `java.util.Set`, `java.util.stream.Collectors`, and `assertEquals`. If you also need to ensure there are no duplicate or extra errors, assert `errors.size() == 2`.

Avoid asserting exact punctuation or version-specific execution IDs in messages. If the application puts stable error codes in `extensions`, match by **(path, business code)** pairs to pinpoint error sources accurately.

## 14. GraphQL @ControllerAdvice and DataFetcherExceptionResolver

Spring for GraphQL provides `DataFetcherExceptionResolver` and supports `@GraphQlExceptionHandler` inside `@ControllerAdvice` to convert exceptions into intentional GraphQL errors.

A production application might define this policy:

- `BookNotFoundException` → business code `BOOK_NOT_FOUND`.
- `AccessDeniedException` → code `FORBIDDEN`, without revealing permission details or owner info.
- Validation exception → code `BAD_REQUEST` with safe metadata.
- Unexpected exception → masked internal error with a correlation ID for private logs, leaking no stack trace/SQL/tokens.

Tests should verify:

~~~text
data field affected  -> null as defined by SDL
errors[].path         -> exact failing field
errors[].extensions   -> stable domain code
errors[].message      -> no sensitive data leaked
siblings              -> preserved or nulled via bubbling per type
~~~

Example assertion when **the API defines** `extensions.code = "BOOK_NOT_FOUND"`:

~~~java
tester.document(document)
        .execute()
        .errors()
        .expect(error ->
                "book".equals(error.getPath())
                && "BOOK_NOT_FOUND".equals(
                        error.getExtensions().get("code")))
        .verify();
~~~

This **illustrates a project-specific policy**, and does not apply to the default in-memory example since it configures no custom error resolver. Without configuring this code, do not write tests expecting the framework to invent `BOOK_NOT_FOUND`.

**Security note:** `errors.extensions` can be visible to clients; never return Java class names, SQL, hostnames, file paths, tokens, or unnecessary internal IDs. Any correlation ID returned in responses should be non-secret and tied to a consistent tracing/logging policy.

## 15. DataLoader, batching, and list paths

When GraphQL uses DataLoader, resolvers can batch multiple IDs and resolve at different times. Error paths still describe **the position in the response**, independent of which DataLoader bean ran or the order database requests were sent.

With a list:

~~~graphql
query {
  orders {
    id
    customer {
      name
    }
  }
}
~~~

If `orders[2].customer.name` fails, the typical response path is:

~~~json
["orders", 2, "customer", "name"]
~~~

If `Customer.name` is Non-Null and `customer` is nullable, null stops at `orders[2].customer`. If `customer: Customer!` and `orders: [Order!]!`, the error bubbles through order and the list to root data. **The schema decides where bubbling stops**, not DataLoader.

When testing DataLoader, use fixtures with deterministic IDs and ordering; beyond data/error paths, test batch call counts, caching, N+1 behavior, and context propagation in dedicated tests. Do not assume batching is optimal merely because the GraphQL response is accurate.

## 16. GraphQL errors and HTTP status: test both layers separately

This table is an interpretation guide, **not a fixed mapping table** for all GraphQL servers:

| Scenario | GraphQL response | HTTP status |
| --- | --- | --- |
| Valid operation, data succeeded | `data`, no errors | Typically 200 |
| Resolver fails on nullable field | Partial `data`, `errors` with `path` | Typically 200 |
| Non-Null bubbles to root | `data: null`, `errors` with `path` | Typically 200 |
| Query syntax/validation error | `errors`, no `data` | Depends on media type/version/transport spec; often 400 or legacy 200 |
| Auth fails before GraphQL handler | May lack GraphQL JSON | HTTP 401/403 from security layer |
| Transport/network/server unavailable | No valid GraphQL response | HTTP 5xx/timeout/network exception |

### 16.1 Do not treat HTTP 200 as business success

A test like:

~~~java
assertEquals(200, response.statusCode());
~~~

only checks HTTP transport. You must also check:

~~~java
JsonNode body = mapper.readTree(response.body());
assertFalse(body.has("errors"));
assertEquals("B-1",
        body.path("data").path("book").path("id").asText());
~~~

Conversely, when **expecting an execution error**, do not assert empty `errors`; assert error count, path, and partial/null data as expected.

### 16.2 Auth errors vs. GraphQL resolver errors

If Spring Security rejects a request before it reaches the GraphQL HTTP handler, the client can receive HTTP 401/403 with a body that does not follow GraphQL response format. Do not force Jackson to parse `data/errors` on every HTTP status.

If a GraphQL resolver checks authorization itself and returns a GraphQL error with a `path`, that is an execution error or custom domain behavior to test per policy. Maintain security integration tests with real users/roles in the test context rather than disabling filters just to make queries PASS.

## 17. When to use @GraphQlTest, @SpringBootTest, or a GraphQlTester variant?

| Test type | Tool | Pros | Limitations |
| --- | --- | --- | --- |
| Resolver/controller + schema/nullability | `@GraphQlTest` + `GraphQlTester` + `@MockitoBean` | Fast, no HTTP server; focused on data/errors | Does not test network/transport or real services |
| Full app without HTTP | `ExecutionGraphQlServiceTester` / GraphQL execution service | Tests GraphQL engine + test context | Does not test TCP or HTTP headers |
| Boot HTTP mock context | `@SpringBootTest(MOCK)` + `@AutoConfigureHttpGraphQlTester` | Tests HTTP handler over mock web client | Does not prove embedded server port/TCP |
| Real HTTP | `@SpringBootTest(RANDOM_PORT)` + `HttpGraphQlTester` or JDK HttpClient | Tests raw request/response and server | Slower; still not production topology |
| Business logic below resolver | JUnit/Mockito or repository slice | Tests rules, data access, and transactions | Does not test GraphQL schema/error paths |
| Subscriptions | `WebSocketGraphQlTester`/`ExecutionGraphQlServiceTester` + `StepVerifier` | Tests GraphQL streams | Differs from single query responses; needs dedicated subscription tests |

**In Spring Boot 3.5.x**, `@GraphQlTest` auto-configures GraphQL execution infrastructure and `GraphQlTester`; it does not scan all `@Service`/`@Repository` beans. Therefore the production `BookCatalog` is absent from the slice, and `@MockitoBean` supplies the collaborator.

With `RANDOM_PORT`, Spring Boot can provide `HttpGraphQlTester` if matching test dependencies are present; our example uses JDK `HttpClient` to inspect raw JSON without adding a WebFlux HTTP tester. Do not assume `@GraphQlTest` checks Spring Security filters or real HTTP status codes.

## 18. GraphQL and SOAP: avoid mixing path/error semantics

The parent knowledge group covers both GraphQL and SOAP, but **this lesson is GraphQL-specific**:

| Topic | GraphQL | SOAP |
| --- | --- | --- |
| Data | JSON `data` per selection set | XML `Envelope` / `Body` |
| Path selection in tests | `GraphQlTester.path("book.title")`, JSONPath | XPath, XML namespaces |
| Application errors | `errors[]` with `message`, `path`, `extensions` | `soap:Fault` with `Code`/`Reason`/`Detail` |
| Partial data | Can contain both `data` and `errors` simultaneously | Depends on WSDL/operation; no GraphQL-style null bubbling |
| Non-Null propagation | Driven by SDL `!` and GraphQL executor | Not directly equivalent to XSD `nillable` |
| Transport | GraphQL can return execution errors with HTTP 200 | SOAP Fault has distinct transport/binding rules |

Do not use `GraphQlTester.errors().expect(...)` to verify a SOAP Fault; use Spring Web Services testing support such as `MockWebServiceClient`, XPath, and SOAP Fault assertions for SOAP. Likewise, do not extrapolate SOAP HTTP status rules to predict GraphQL errors.

## 19. Common mistakes when testing GraphQL data/errors/nullability

**1. Asserting only HTTP status 200.**  
Resolvers can fail and return partial `data` with `errors`. Assert both the error list and data.

**2. Using `path("data.book.id")` in GraphQlTester.**  
`GraphQlTester.path` starts at `data`, so use `path("book.id")`.

**3. Confusing `isNull()` with `valueIsNull()`.**  
Spring GraphQL 1.x `GraphQlTester.Path` uses `valueIsNull()` and `pathDoesNotExist()`. Verify the API for your version.

**4. Equating a missing field with JSON null.**  
An unselected field is omitted from the response; a selected nullable field can be null. Test both when the schema contract matters.

**5. Seeing `book:null` and concluding the record doesn't exist.**  
`book` can also become null because a Non-Null child failed. Read `errors.path` to tell them apart.

**6. Seeing `errors.path=["book","title"]` and expecting `data.book.title` to remain null.**  
When `title:String!` fails, nullable `book` itself becomes null as a whole object; the `title` field no longer exists under `book`.

**7. Testing `[Book!]!` the same as `[Book]`.**  
With `[Book!]!` one broken item can turn `data:null`; with `[Book]` only that item becomes null.

**8. Hardcoding errors array order.**  
A query with multiple fields may resolve concurrently. Compare sets of paths/codes and assert count instead of relying on arbitrary error indices.

**9. Asserting exact internal error messages.**  
Spring GraphQL may mask exceptions. Test application-defined domain error codes and paths rather than stack traces or execution IDs.

**10. Using `filter(...)` to prove a mandatory error exists.**  
`filter` passes even with zero errors. Use `expect(...)` or `satisfy(...)` with count/path assertions.

**11. Writing an empty `satisfy(errors -> {})`.**  
It marks every error as handled while proving nothing. Always assert the expected count and attributes.

**12. Forgetting that GraphQlTester rejects unexpected errors when reading a data path.**  
For intentional partial-data errors, inspect `errors` first and then `path(...)`. For happy paths, call `errors().verify()` explicitly.

**13. Asserting `hasValue()` on an empty list.**  
`hasValue()` requires a non-null value or non-empty list. `[]` is valid; use `entityList(...).hasSize(0)`.

**14. Confusing GraphQL ID with numeric Java types.**  
GraphQL `ID` typically serializes as a string, even if backed by a numeric column. Test against the GraphQL schema/response representation, not the DB column type.

**15. Mocking the resolver itself under test.**  
Mocking the controller or GraphQL source prevents testing mappings. Mock the collaborator `BookCatalog` in the slice and keep `BookGraphQlController` real.

**16. Expecting @GraphQlTest to load every @Service.**  
Test slices apply filters. Use `@MockitoBean`, test beans, or `@Import` intentionally; use an integration test if real services/repositories are required.

**17. Confusing request validation errors with output Non-Null errors.**  
Invalid queries skip resolvers and omit `data`; output Non-Null errors occur after execution and can return `data:null`.

**18. Assuming every HTTP 4xx/5xx is a GraphQL error.**  
Security gateways, proxies, and transports can return HTML or plain text. Check Content-Type and status before deserializing as a GraphQL response.

**19. Treating Java exception messages as public API.**  
Never expose SQL, stack traces, or credentials. Error messages/codes need a clear policy; tests should avoid asserting framework-specific technical wording.

**20. Believing SDL nullability tests guarantee clean DB data.**  
The GraphQL executor catches violations at request time, yet bad data can still exist in storage. Add domain/persistence validation tests to prevent invalid data early.

## 20. Reliable workflow for testing a GraphQL query

1. **Read the SDL first:** identify which fields are nullable/Non-Null and whether list items can be null.
2. **Define realistic operations:** include query name, variables, aliases, and selection sets.
3. **Pick the test layer:** `@GraphQlTest` for resolvers/schema; HTTP integration for protocol and raw responses.
4. **Prepare fixtures:** happy path, not found, nullable null, resolver error, Non-Null violation, failing list item.
5. **Assert no-error paths:** data fields + `errors().verify()`.
6. **Assert valid nulls:** `valueIsNull()` + no errors.
7. **Assert omitted fields:** `pathDoesNotExist()` when a field is not selected.
8. **Assert execution errors:** `errors().expect(...)` or `satisfy(...)` with exact path and error count.
9. **Assert bubbling:** parent/list/root is null **at the right level** per SDL; check whether siblings survive.
10. **Assert aliases/list indices:** parsed path with aliases and 0-based integer indices.
11. **Test request validation errors separately:** no `data`, resolver not invoked, transport status per contract.
12. **Avoid internal messages/order:** favor domain error codes, parsed paths, and non-leakage.
13. **Test live HTTP when needed:** Content-Type, status, JSON `data`/`errors`; keep tests independent of production DBs.
14. **Test DataLoader/transactions/security at their own layers:** do not infer them from a `GraphQlTester` slice test.
15. **Keep CI stable:** compatible versions, deterministic fixtures, random ports, and sensible timeouts.

### Pre-commit checklist

- [ ] Distinguished `data:null` from missing `data` key.
- [ ] Distinguished an absent field from a field with JSON null.
- [ ] Data paths use `GraphQlTester.path` without a `data.` prefix.
- [ ] Error paths use `getParsedPath()` to check strings and integer indices.
- [ ] Aliases update the root field name in error paths.
- [ ] When an execution error is intentional, the test handles errors before inspecting data.
- [ ] When no errors are expected, the test verifies no unexpected errors occurred.
- [ ] SDL `T!`, `[T]`, `[T!]`, `[T]!`, `[T!]!` are understood and tested for proper null propagation.
- [ ] Empty lists `[]` are not treated as null or errors.
- [ ] Request errors, resolver errors, and Non-Null errors have separate tests.
- [ ] Tests do not hardcode internal messages, execution IDs, or unguaranteed error ordering.
- [ ] Business error codes in `extensions` are asserted only when the real API enforces that policy.
- [ ] Spring test slice keeps the real resolver and mocks collaborators properly.
- [ ] HTTP integration tests verify both transport and raw GraphQL JSON.
- [ ] Secrets, tokens, SQL, and sensitive data are never leaked in GraphQL errors.
- [ ] Domain/DB/security layers have tests if risks lie outside the GraphQL schema.

**Key takeaway:** in GraphQL, seeing a field return `null` **is not enough** to tell whether it failed; read it alongside **SDL nullability** and **`errors.path`**. When a Non-Null field fails, `null` can bubble to an object, a list, or all of `data`, while `errors.path` still pinpoints the deep origin of the error. `GraphQlTester` makes testing data paths and expected errors clear; HTTP integration tests verify the exact JSON response when data is wiped by null propagation.

### Official references

- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html): `GraphQlTester`, `errors().expect/filter/satisfy/verify`, and transports.
- [Spring for GraphQL 1.3.x — GraphQlTester.Path API](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/test/tester/GraphQlTester.Path.html): `hasValue`, `valueIsNull`, `pathDoesNotExist`, `entity`, and `entityList`.
- [Spring for GraphQL 1.3.x — GraphQlTester.Errors API](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/test/tester/GraphQlTester.Errors.html): `expect` vs `filter`, `satisfy`, `verify`.
- [Spring GraphQL ResponseError API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/ResponseError.html): `getPath`, `getParsedPath`, `getExtensions`, `getLocations`.
- [Spring Boot 3.5 — Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@GraphQlTest`, dependency injection, and `HttpGraphQlTester`.
- [GraphQL Specification — Response](https://spec.graphql.org/September2025/#sec-Response): `data`/`errors`, field errors, error paths, and request errors.
- [GraphQL Specification — Handling Execution Errors](https://spec.graphql.org/September2025/#sec-Handling-Execution-Errors): Non-Null bubbling across objects, lists, and root.
- [GraphQL Java — Data Fetching](https://graphql-java.com/documentation/data-fetching/): default PropertyDataFetcher and POJO field extraction.
- [GraphQL.org — Response](https://graphql.org/learn/response/): partial data, execution errors, and top-level response keys.