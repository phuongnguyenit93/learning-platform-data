# GraphQlTester for Queries, Mutations, and Input Variables in Spring Boot

## Objectives

In Spring Boot, GraphQL lets clients send a **document** containing `query`, `mutation` (or `subscription`) operations and select the exact fields to read. When testing, sending an HTTP POST to `/graphql` and only checking status 200 is not enough: a GraphQL response can carry **`errors` even when the HTTP transport succeeds**, and a mutation that returns the expected payload might not have produced the right side effect.

`GraphQlTester` from the **Spring for GraphQL Test** library provides a unified testing API: send GraphQL documents, pass variables, execute operations, inspect **`data` via JSONPath**, verify `errors`, and check query/mutation outcomes. The same assertion style works against an in-process GraphQL engine or over an HTTP client when you choose the right tester variant.

After this lesson, you can:

- Distinguish `query`, `mutation`, `variables`, `operationName`, the GraphQL schema, and the selection set.
- Write `GraphQlTester.document(...).variable(...).execute().path(...).entity(...).isEqualTo(...)` tests.
- Reuse documents via `documentName(...)` and `src/test/resources/graphql-test/*.graphql`.
- Pass `ID!`, `String!`, `Int!` scalars and `BookInput!` input objects using `variable`/`variables(Map)`.
- Assert nested objects, lists, `null` fields, absent fields, and result count/ordering.
- Verify mutations for **both their response and their state changes** via a follow-up query or appropriate persistence layer.
- Distinguish **GraphQL request/validation/execution** errors from HTTP transport errors; use `errors().expect/filter/satisfy`.
- Choose `@GraphQlTest`/`ExecutionGraphQlServiceTester` for a GraphQL slice, or `@SpringBootTest(RANDOM_PORT)`/`HttpGraphQlTester` for HTTP integration.
- Run a complete Java 17 + Spring Boot 3.3.5 + JUnit Jupiter + Gradle example with schema, controller, in-memory service, query, mutation, and isolated tests.

This article belongs to the **Spring Boot – testing** module, **GraphQL and SOAP** section. The content focuses on **GraphQL**: SOAP uses a different protocol and message model, so do not use `GraphQlTester` to test SOAP envelopes, WSDLs, or SOAP Faults.

## 1. From HTTP request to GraphQL response

A typical GraphQL request contains the following parts:

~~~graphql
query FindBook($id: ID!) {
  book(id: $id) {
    id
    title
    pages
  }
}
~~~

This is a **GraphQL document** with an operation named `FindBook`. The `$id` declares a variable of type `ID!` (non-null), and `book(id: $id)` passes the variable value into the resolver argument. The client must send variables alongside it, for example:

~~~json
{
  "query": "query FindBook($id: ID!) { book(id: $id) { id title pages } }",
  "variables": {
    "id": "b1"
  },
  "operationName": "FindBook"
}
~~~

Over HTTP, GraphQL typically uses `POST /graphql` with Content-Type `application/json`. This HTTP body is a **GraphQL-over-HTTP request**, not a REST endpoint like `GET /api/books/b1`.

If the book exists, an illustrative GraphQL response looks like:

~~~json
{
  "data": {
    "book": {
      "id": "b1",
      "title": "Java 17",
      "pages": 300
    }
  }
}
~~~

If the ID does not exist and the schema declares `book(...): Book` (nullable), a valid response can be:

~~~json
{
  "data": {
    "book": null
  }
}
~~~

On a validation or execution error, the response may contain:

~~~json
{
  "data": null,
  "errors": [
    {
      "message": "GraphQL error description appears here"
    }
  ]
}
~~~

This response is **structural illustration only**, not the exact message from a specific Spring GraphQL version. Errors can also include `locations`, `path`, `extensions`, and classification types. Some errors still allow partial `data` to exist; do not equate "has errors" with "data is definitely null."

### What do queries and mutations mean?

| Element | Role | Example |
| --- | --- | --- |
| `query` | Reads data; servers are normally designed to avoid side effects | `book(id: "b1")`, `books` |
| `mutation` | Requests a state change | `addBook(input: ...)` |
| `subscription` | Event stream over time | `bookAdded` |
| `variables` | Values passed separately from the document | `id`, `input` |
| `selection set` | The fields the client wants in the response | `{ id title pages }` |
| `operationName` | Picks an operation when a document defines multiple operations | `FindBook` |
| `schema` | Server contract of types/fields/arguments | `type Query`, `input BookInput` |

GraphQL **does not guarantee that a mutation automatically runs in a single DB transaction**. A mutation is an operation intending to modify state; commits, rollbacks, and test data cleanup must be verified at the data layer when the system has side effects.

## 2. Why use `GraphQlTester` instead of comparing JSON strings?

Using a raw HTTP client, a test might write:

~~~java
assertEquals(200, response.statusCode());
~~~

This assertion only states that the HTTP transport returned status 200. The GraphQL engine can return 200 along with `errors` or wrong `data`. Comparing raw JSON strings is also brittle: property order and whitespace are not always part of the contract.

`GraphQlTester` lets you write:

~~~java
graphQlTester.document("""
        query FindBook($id: ID!) {
          book(id: $id) {
            id
            title
            pages
          }
        }
        """)
        .variable("id", "b1")
        .execute()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Java 17");
~~~

This is a snippet inside a Spring GraphQL test where `graphQlTester` is configured. It describes executing the document, sending the `id` variable, then accessing **`data.book.title`** and asserting the String value.

Notably: `path("book.title")` **is evaluated relative to the `data` section** of the GraphQL response. Do not write `path("data.book.title")` as if the path started at the root HTTP JSON body.

### Intentional call chain

~~~text
GraphQlTester
    |
    +-- document("query ...") or documentName("findBook")
    |
    +-- variable("id", "b1")
    |
    +-- execute()    -> sends operation, receives GraphQL response
    |
    +-- errors()     -> inspects errors if errors are expected
    |
    +-- path("book.title")
    |      |
    |      +-- entity(String.class)
    |               |
    |               +-- isEqualTo("Java 17")
    |
    +-- path("books[*].title").entityList(String.class)
~~~

Unlike Reactor's `StepVerifier`, `GraphQlTester` is a direct API for **GraphQL request/response**. Do not use `StepVerifier` in place of GraphQL `data`/`errors` assertions when testing a normal query or mutation.

## 3. Choosing the right tester variant

Spring for GraphQL shares a common interface `org.springframework.graphql.test.tester.GraphQlTester`, while implementations differ in **where the request executes**.

| Tester/environment | Real HTTP server? | What does it verify? | When should you use it? |
| --- | --- | --- | --- |
| `ExecutionGraphQlServiceTester` | No | GraphQL execution, schema, resolvers/data fetchers | Server-side unit/slice tests |
| `WebGraphQlTester` | No HTTP needed | `WebGraphQlHandler` and `WebGraphQlInterceptor` in a server-side context | Testing `WebGraphQlHandler` specifics |
| `HttpGraphQlTester` | Can have or not, depending on `WebTestClient` binding | GraphQL over HTTP transport, headers, optional authentication | HTTP/GraphQL integration |
| `WebSocketGraphQlTester` | WebSocket communication | GraphQL over WebSocket, especially subscriptions | WebSocket/subscription tests |
| `RSocketGraphQlTester` | RSocket transport | GraphQL over RSocket | Systems using RSocket |

In **Spring Boot 3.3.x**:

- `@GraphQlTest(BookGraphQlController.class)` creates a GraphQL test slice **without transport/server**, configuring a server-side `GraphQlTester` bean for testing controllers/resolvers.
- `@SpringBootTest(webEnvironment = RANDOM_PORT)` starts a real HTTP server; with appropriate test dependencies, Boot can provide an `HttpGraphQlTester` connected to the application server.
- `@SpringBootTest(webEnvironment = MOCK)` does not open a real port; if you want an HTTP tester against a mock web environment, use `@AutoConfigureHttpGraphQlTester` and configure the tester accordingly.
- When building `HttpGraphQlTester` manually, you need a `WebTestClient` bound to the proper base URL or application context.

**Do not call `@GraphQlTest` an end-to-end HTTP test.** It is very valuable because it tests the real GraphQL schema, argument binding, and resolvers without opening a socket, but it does not prove HTTP routes, proxies, authentication filters, CORS, SSL, or network responses.

### `@GraphQlTest` does not scan the entire application

A test slice has a limited scan scope, typically focusing on `@Controller`, GraphQL runtime wiring, and supporting components. Regular services and repositories **are not all automatically available** in the slice. You can:

- Use `@MockBean` in Spring Boot 3.3 to mock controller dependencies.
- Use `@Import(BookCatalog.class)` to include a real service or fake when you want to verify behavior.
- Use `@TestConfiguration` with purposefully registered beans.
- Switch to `@SpringBootTest` if you truly need full application wiring, DB, or infrastructure.

The runnable example below uses `@Import(BookCatalog.class)`: the service stores data in memory and runs real logic without relying on a database or mocks. This also makes mutation side effects observable.

## 4. `variable` and `variables`: the data type contract

A GraphQL operation can declare multiple variables:

~~~graphql
mutation AddBook($input: BookInput!) {
  addBook(input: $input) {
    id
    title
    pages
  }
}
~~~

Here:

- `$input` is a **variable** named in the document.
- `BookInput` is an **input object type** in the GraphQL schema, not a Java type chosen freely by the client.
- The `!` means **non-null**. If a required variable is missing or null is passed, GraphQL validation/variable coercion can reject the request **before the resolver runs**.
- Fields of `BookInput` can also be marked `String!`, `Int!` to enforce valid non-null values.
- GraphQL `Int` is normally a signed 32-bit integer; the Java service must pick an appropriate type and bounds.

In a Java test:

~~~java
Map<String, Object> input = Map.of(
        "title", "GraphQL Testing",
        "pages", 180);

graphQlTester.documentName("addBook")
        .variable("input", input)
        .execute()
        .path("addBook.title")
        .entity(String.class)
        .isEqualTo("GraphQL Testing");
~~~

This snippet is based on the `addBook.graphql` document file in section 7. `GraphQlTester` builds a properly structured GraphQL request when passing a `Map` as an input object, avoiding manual JSON string concatenation.

### Passing multiple variables

~~~java
graphQlTester.document("""
        query Search($prefix: String!, $limit: Int!) {
          searchBooks(prefix: $prefix, limit: $limit) {
            id
          }
        }
        """)
        .variables(Map.of("prefix", "Sp", "limit", 5))
        .execute();
~~~

This snippet **only illustrates the syntax** of `variables(Map)`; the runnable project does not define a `searchBooks` field. In Spring for GraphQL 1.3.x, `variables(Map)` adds multiple variables at once; if using an older API, check the Javadoc for that version.

### `null` vs. an omitted variable

GraphQL distinguishes three cases:

1. The variable is **not provided** in `variables`.
2. The variable is provided with **null**.
3. The variable is provided with an actual value.

For `ID!` or `BookInput!`, both cases 1 and 2 are invalid unless there is a suitable default. For nullable arguments, the semantics can differ: an omitted input field can mean "leave unchanged," whereas a field explicitly set to null can mean "clear the value."

Java's `Map.of(...)` **does not accept null**; if you need to send null:

~~~java
graphQlTester.document("""
        query Optional($id: ID) {
          maybeBook(id: $id) { id }
        }
        """)
        .variable("id", null)
        .execute();
~~~

This is an illustrative snippet; the `maybeBook` field does not exist in the section 7 project. `variable("id", null)` expresses a GraphQL null explicitly. A thorough test checks both the schema and the resolver contract for null and omitted values, rather than testing only one case.

### Avoid concatenating variables directly into the GraphQL document

Weak pattern:

~~~java
String query =
        "{ book(id: \"" + userSuppliedId + "\") { title } }";
~~~

If the ID contains quotes, special characters, or user-controlled content, the document can break syntax or alter the query structure. **Passing data via `variable`** separates the query document from input, making it reusable, type-checked, and easier to maintain. This is a sound design principle, though you still need authorization checks, pagination, and query complexity limits on the server.

## 5. Checking `data` with `path`, `entity`, `entityList`

### 5.1. Scalar fields

~~~java
graphQlTester.document("{ book(id: \"b1\") { title } }")
        .execute()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Java 17");
~~~

`path("book.title")` inspects `data.book.title`. When there is an unhandled GraphQL error, accessing a path normally fails the assertion instead of silently treating the response as successful.

### 5.2. Nested objects and multiple fields

If the document selects:

~~~graphql
query {
  book(id: "b1") {
    id
    title
    pages
  }
}
~~~

You can verify the paths:

~~~java
var response = graphQlTester.document("""
        { book(id: "b1") { id title pages } }
        """)
        .execute();

response.path("book.id")
        .entity(String.class)
        .isEqualTo("b1");

response.path("book.title")
        .entity(String.class)
        .isEqualTo("Java 17");

response.path("book.pages")
        .entity(Integer.class)
        .isEqualTo(300);
~~~

`response` is a `GraphQlTester.Response` and can navigate multiple paths from a single execution. This avoids running the same query three times.

### 5.3. Result lists

With schema `books: [Book!]!`, document:

~~~graphql
query {
  books {
    id
    title
  }
}
~~~

Test:

~~~java
graphQlTester.document("""
        { books { id title } }
        """)
        .execute()
        .path("books[*].title")
        .entityList(String.class)
        .containsExactly("Java 17", "Spring Boot");
~~~

`containsExactly` checks **content and order** in the corresponding list assertion API. If the schema or backend does not guarantee order, do not write assertions relying on incidental database ordering. Instead, add an explicit sort argument or assert the set of values in an order-independent way.

`hasSize(2)` only checks the element count; `containsExactly` is stronger when all expected items are known. `contains(...)` only requires the listed values to be present and does not prove there are no extra elements.

### 5.4. Null fields, absent fields, and empty lists

Suppose `book(id: "missing")` returns `null` without an error:

~~~java
graphQlTester.document("""
        { book(id: "missing") { id title } }
        """)
        .execute()
        .path("book")
        .valueIsNull();
~~~

`valueIsNull()` verifies that the GraphQL response has a **null value at that path**. It differs from:

- `pathDoesNotExist()`: the path is not represented in the `data` tree, for instance because the field was not requested in the selection set.
- `hasValue()`: has a non-null value or a non-empty list.
- `entityList(...).hasSize(0)`: the field is an empty list, **not null**.

In GraphQL, a field omitted from the selection set normally **does not appear in `data`**, even though the schema defines it. Therefore, asserting an absent path is only right when the document omits that field or the contract dictates absence, not as a way to check "book not found" when the resolver returns null.

## 6. GraphQL errors: do not equate HTTP 200 with success

A GraphQL response can contain `errors` due to:

- Invalid document syntax.
- Selecting a field not present in the schema.
- Missing required variables, wrong variable types, or invalid input objects.
- A resolver throwing an exception during processing.
- Authorization failure inside a data fetcher.
- Timeout, unavailable database, or downstream failure.

For **schema validation/variable coercion** errors, the GraphQL engine typically rejects the operation before any resolver runs. For **execution errors**, **partial data** may be present and the error only affects one field branch (depending on GraphQL non-null propagation).

### By default GraphQlTester helps catch errors

During standard `path(...)` assertions, `GraphQlTester` verifies that the response has no **unhandled** GraphQL errors. Thus a test with the "right title but errors on another field" will fail; this is usually desirable.

Do not "fix" it by filtering out all errors:

~~~java
// WEAK PATTERN: filters every error, potentially hiding regressions.
response.errors()
        .filter(error -> true)
        .verify();
~~~

A filter does not require an error to occur and can mask unexpected failures. If a test truly expects a specific error, use `expect` or `satisfy` with a clear condition.

### `errors().expect(...)` when an error must appear

~~~java
graphQlTester.document("""
        query Broken {
          book(id: "b1") { nonExistingField }
        }
        """)
        .execute()
        .errors()
        .expect(error -> error.getMessage() != null
                && !error.getMessage().isBlank())
        .verify();
~~~

This document is **intentionally invalid** against the demo schema, so the engine must return at least one GraphQL error. The example checks for a non-blank message so it does not depend on exact GraphQL Java wording; in a real system, check stable types/codes/locations/paths when they are part of the contract. `expect` differs from `filter`: if no error matches the predicate, the test **fails**.

### `errors().satisfy(...)` to inspect the error list

~~~java
graphQlTester.document("""
        query FindBook($id: ID!) {
          book(id: $id) { id }
        }
        """)
        .execute()
        .errors()
        .satisfy(errors -> {
            assertFalse(errors.isEmpty());
            errors.forEach(error ->
                    assertFalse(error.getMessage().isBlank()));
        });
~~~

This snippet lives inside a JUnit method with a static import of `assertFalse`. Because the required `id` variable is omitted, GraphQL variable coercion must report an error. `satisfy` lets you inspect all errors and marks them as handled; when using it, make sure to actually assert inside the lambda so it does not become a silent error-ignoring no-op.

### `errors().filter(...)` when a known error is permitted

Suppose a response has a **permitted** error on a secondary field, while the test still checks other `data`:

~~~java
graphQlTester.document(document)
        .execute()
        .errors()
        .filter(error -> error.getMessage()
                .contains("KNOWN_OPTIONAL_FIELD"))
        .verify()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Java 17");
~~~

This snippet **illustrates a pattern**, requiring a valid `document` and a resolver producing that exact error. There is no `KNOWN_OPTIONAL_FIELD` in the demo. Use `filter` only when business requirements genuinely allow partial data and you know precisely which error is acceptable. A global `errorFilter` on the tester builder has an even broader effect, making it easy to lose coverage if used carelessly.

### HTTP status and GraphQL errors are two separate layers

- **HTTP transport:** did the request reach the GraphQL endpoint? What are the body Content-Type, auth, timeout, proxy, and status?
- **GraphQL request:** does the document match the schema, are variables typed properly, is the operation allowed?
- **GraphQL execution:** did the data fetcher return the right data, and how are business errors mapped?

Depending on the GraphQL-over-HTTP specification version, protocol response, and error kind, HTTP may use status 200 or 4xx. **Do not hardcode a rule that "every GraphQL error is always HTTP 200."** When testing with an in-process `GraphQlTester`, focus on `data/errors`; when you need to check deployment HTTP status/headers, add an appropriate HTTP integration test.

## 7. Complete Java 17/Spring Boot 3.3.5 project

The example runs without a database or Docker. A `BookCatalog` stores books in memory and exposes GraphQL operations:

- `Query.book(id: ID!): Book` returns a book or null when not found.
- `Query.books: [Book!]!` returns the list of books sorted by ID.
- `Mutation.addBook(input: BookInput!): Book!` adds a book and returns the newly created book.
- `BookInput` has `title: String!` and `pages: Int!`.

Tests use scalar variables, an input object `Map`, document files, mutations, and follow-up queries verifying side effects. Because of mutable state, tests reset the fixture before and after each method and **must not enable parallel method execution on the same context** without additional isolation.

### 7.1. Project structure

~~~text
graphql-tester-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/
    │   ├── java/com/example/graphql/
    │   │   ├── GraphQlApplication.java
    │   │   ├── BookCatalog.java
    │   │   └── BookGraphQlController.java
    │   └── resources/graphql/
    │       └── schema.graphqls
    └── test/
        ├── java/com/example/graphql/
        │   ├── BookGraphQlSliceTest.java
        │   └── BookGraphQlHttpTest.java
        └── resources/graphql-test/
            ├── bookById.graphql
            └── addBook.graphql
~~~

Use the exact package, file, and resource names. Gradle Wrapper scripts and the binary JAR are generated by Gradle or taken from the repo; the example omits the binary contents of `gradle-wrapper.jar`.

**`settings.gradle`**:

~~~groovy
rootProject.name = 'graphql-tester-demo'
~~~

**`build.gradle`** (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.graphql:spring-graphql-test'

    // HTTP GraphQlTester uses WebTestClient.
    // In this demo the app still uses Servlet MVC because starter-web is present.
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux'

    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Explanation:

- `spring-boot-starter-graphql` provides GraphQL server integration.
- `spring-boot-starter-web` provides the Spring MVC/Servlet HTTP transport for the GraphQL endpoint. **The GraphQL starter alone does not automatically give every app an HTTP server** if a web transport is missing.
- `spring-graphql-test` provides `GraphQlTester`, its variants, and testing APIs.
- `spring-boot-starter-test` provides JUnit Jupiter/Spring TestContext.
- `spring-boot-starter-webflux` in **testImplementation** supplies `WebTestClient` for `HttpGraphQlTester`; the production app stays Servlet MVC in this combined setup.
- `useJUnitPlatform()` lets Gradle discover and run `@Test` methods.
- Boot 3.3.5 dependency management keeps Spring GraphQL and GraphQL Java compatible; avoid pinning separate versions that cause API drift.

If the project is already a WebFlux application, the webflux dependency belongs in `implementation` and does not need to be added again in test scope. In projects on other Boot versions, check the **exact documentation and package APIs**; Boot 3.3 uses `@MockBean` in tests when mocking is needed, while newer lines provide `@MockitoBean`.

### 7.2. GraphQL schema as the source contract

**`src/main/resources/graphql/schema.graphqls`**:

~~~graphql
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Mutation {
  addBook(input: BookInput!): Book!
}

type Book {
  id: ID!
  title: String!
  pages: Int!
}

input BookInput {
  title: String!
  pages: Int!
}
~~~

Explanation:

- Root `Query` has `book` and `books`.
- `book` is nullable: when not found it returns GraphQL null without necessarily reporting an error.
- `books` is a non-null list of non-null `Book` items. An empty list `[]` is valid.
- Root `Mutation` has `addBook`.
- `input BookInput` is **distinct from** `type Book`: input types are used for arguments, output types for selection sets.
- `ID` is the GraphQL identifier scalar; the Java demo handles it as `String`.
- `Int` is a signed 32-bit integer scalar; Java `int` fits the demo, not arbitrary precision.

Spring Boot 3.3 automatically locates schemas under classpath `graphql/**` in standard configuration. If you place schemas in another directory, configure `spring.graphql.schema.locations` accordingly.

### 7.3. Spring Boot main class

**`src/main/java/com/example/graphql/GraphQlApplication.java`**:

~~~java
package com.example.graphql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GraphQlApplication {

    public static void main(String[] args) {
        SpringApplication.run(GraphQlApplication.class, args);
    }
}
~~~

Place the main class in the parent package so Boot component scanning finds `BookCatalog` and `BookGraphQlController`.

### 7.4. In-memory service with deterministic fixtures

**`src/main/java/com/example/graphql/BookCatalog.java`**:

~~~java
package com.example.graphql;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Service;

@Service
public class BookCatalog {

    private final Map<String, Book> books =
            new ConcurrentHashMap<>();

    private final AtomicInteger sequence =
            new AtomicInteger(2);

    public BookCatalog() {
        reset();
    }

    // Fixture for demo/test; production should use a repository
    // or an appropriate state management mechanism.
    public synchronized void reset() {
        books.clear();

        books.put("b1", new Book("b1", "Java 17", 300));
        books.put("b2", new Book("b2", "Spring Boot", 250));

        sequence.set(2);
    }

    public Book findById(String id) {
        return books.get(id);
    }

    public List<Book> findAll() {
        List<Book> result = new ArrayList<>(books.values());
        result.sort(Comparator.comparing(Book::getId));
        return List.copyOf(result);
    }

    public Book addBook(BookInput input) {
        if (input == null
                || input.title() == null
                || input.title().isBlank()
                || input.pages() <= 0) {
            throw new IllegalArgumentException(
                    "invalid book input");
        }

        String id = "b" + sequence.incrementAndGet();

        Book book = new Book(
                id, input.title(), input.pages());

        books.put(id, book);
        return book;
    }

    public record BookInput(String title, int pages) {
    }

    public static final class Book {

        private final String id;
        private final String title;
        private final int pages;

        public Book(String id, String title, int pages) {
            this.id = id;
            this.title = title;
            this.pages = pages;
        }

        public String getId() {
            return id;
        }

        public String getTitle() {
            return title;
        }

        public int getPages() {
            return pages;
        }
    }
}
~~~

**Test-oriented design choices:**

- `reset()` seeds the exact two base books `b1` and `b2`, making expected results deterministic.
- `findAll()` sorts by ID so list tests do not depend on `ConcurrentHashMap` iteration order.
- `addBook` generates IDs via a sequence; the mutation creates a **real state change**, not just returning a fake DTO.
- `BookInput` is a Java record; the Spring GraphQL argument binder binds the GraphQL input object to this record.
- `Book` exposes JavaBean getters `getId`, `getTitle`, `getPages` so the GraphQL data fetcher resolves the fields.
- Because the service is a mutable singleton, tests call `reset` in lifecycle hooks. **Do not run tests that mutate the service in parallel** without isolating context or state.

The in-memory dataset keeps the focus on GraphQL. It does not prove transactions, JPA, database commits, or concurrent mutation consistency in a production system.

### 7.5. GraphQL controller with `@QueryMapping` and `@MutationMapping`

**`src/main/java/com/example/graphql/BookGraphQlController.java`**:

~~~java
package com.example.graphql;

import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

import com.example.graphql.BookCatalog.Book;
import com.example.graphql.BookCatalog.BookInput;

@Controller
public class BookGraphQlController {

    private final BookCatalog catalog;

    public BookGraphQlController(BookCatalog catalog) {
        this.catalog = catalog;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return catalog.findById(id);
    }

    @QueryMapping
    public List<Book> books() {
        return catalog.findAll();
    }

    @MutationMapping
    public Book addBook(
            @Argument("input") BookInput input) {
        return catalog.addBook(input);
    }
}
~~~

These annotations belong to Spring GraphQL:

- `@QueryMapping` maps the resolver to the matching field on the root `Query` by method name.
- `@MutationMapping` maps the resolver to root `Mutation`.
- `@Argument("id")` retrieves the `id` argument already processed by GraphQL Java from the document/variables.
- `@Argument("input")` retrieves the input object and binds it to `BookInput`.
- Specifying argument names explicitly avoids relying on parameter-name build metadata.

**Note:** When `BookCatalog.addBook` throws `IllegalArgumentException` due to a business rule, GraphQL execution can surface a generic error or be handled by a custom `DataFetcherExceptionResolver`/`@GraphQlExceptionHandler`. The demo focuses on **valid queries/mutations** and **schema/required-variable errors**; it does not claim business exceptions automatically map to a fixed error code without a configured error resolver.

### 7.6. Storing operations in `graphql-test/`

**`src/test/resources/graphql-test/bookById.graphql`**:

~~~graphql
query FindBook($id: ID!) {
  book(id: $id) {
    id
    title
    pages
  }
}
~~~

**`src/test/resources/graphql-test/addBook.graphql`**:

~~~graphql
mutation AddBook($input: BookInput!) {
  addBook(input: $input) {
    id
    title
    pages
  }
}
~~~

With `GraphQlTester.documentName("bookById")`, the tester searches for a document resource named `bookById` with extension `.graphql` (or `.gql` where supported) in the default **`graphql-test/`** classpath folder. This directory is separate from `src/main/resources/graphql/`: main resources hold the **schema**, while test resources hold **client operations**.

Advantages of document files:

- IDE syntax highlighting and validation can be used.
- Easy reuse of the same query across multiple tests.
- Avoids long String literals and repeated selection sets.
- The `variables` part changes in tests without modifying the query.

If multiple operations live in the same document, select the target one with `operationName("...")` for that request. In this example, each file contains a single operation, so calling `operationName` is unnecessary.

## 8. JUnit GraphQL slice test: query, mutation, and variables

**`src/test/java/com/example/graphql/BookGraphQlSliceTest.java`**:

~~~java
package com.example.graphql;

import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@GraphQlTest(BookGraphQlController.class)
@Import(BookCatalog.class)
class BookGraphQlSliceTest {

    @Autowired
    private GraphQlTester tester;

    @Autowired
    private BookCatalog catalog;

    @BeforeEach
    void setUp() {
        catalog.reset();
    }

    @AfterEach
    void cleanUp() {
        catalog.reset();
    }

    @Test
    void queryUsesNamedDocumentAndIdVariable() {
        tester.documentName("bookById")
                .variable("id", "b1")
                .execute()
                .path("book.title")
                .entity(String.class)
                .isEqualTo("Java 17");
    }

    @Test
    void queryChecksMultipleSelectedFields() {
        var response = tester.document("""
                query GetBook($id: ID!) {
                  book(id: $id) {
                    id
                    title
                    pages
                  }
                }
                """)
                .variable("id", "b2")
                .execute();

        response.path("book.id")
                .entity(String.class).isEqualTo("b2");

        response.path("book.title")
                .entity(String.class).isEqualTo("Spring Boot");

        response.path("book.pages")
                .entity(Integer.class).isEqualTo(250);
    }

    @Test
    void queryMissingBookReturnsNullNotError() {
        tester.documentName("bookById")
                .variable("id", "missing")
                .execute()
                .path("book")
                .valueIsNull();
    }

    @Test
    void queryListChecksValuesAndOrdering() {
        tester.document("""
                query AllBooks {
                  books { id title }
                }
                """)
                .execute()
                .path("books[*].title")
                .entityList(String.class)
                .containsExactly("Java 17", "Spring Boot");
    }

    @Test
    void queryCanUseVariablesMap() {
        tester.documentName("bookById")
                .variables(Map.of("id", "b1"))
                .execute()
                .path("book.pages")
                .entity(Integer.class)
                .isEqualTo(300);
    }

    @Test
    void mutationAcceptsInputObjectVariable() {
        tester.documentName("addBook")
                .variable("input", Map.of(
                        "title", "GraphQL Testing",
                        "pages", 180))
                .execute()
                .path("addBook.title")
                .entity(String.class)
                .isEqualTo("GraphQL Testing");
    }

    @Test
    void mutationChangesStateVisibleToNextQuery() {
        String id = tester.documentName("addBook")
                .variable("input", Map.of(
                        "title", "JUnit Jupiter",
                        "pages", 210))
                .execute()
                .path("addBook.id")
                .entity(String.class)
                .get();

        assertNotNull(id);
        assertTrue(id.startsWith("b"));

        tester.documentName("bookById")
                .variable("id", id)
                .execute()
                .path("book.title")
                .entity(String.class)
                .isEqualTo("JUnit Jupiter");
    }

    @Test
    void mutationResultHasAllExpectedFields() {
        var response = tester.documentName("addBook")
                .variable("input", Map.of(
                        "title", "Spring GraphQL",
                        "pages", 150))
                .execute();

        response.path("addBook.id")
                .entity(String.class).isEqualTo("b3");

        response.path("addBook.title")
                .entity(String.class).isEqualTo("Spring GraphQL");

        response.path("addBook.pages")
                .entity(Integer.class).isEqualTo(150);
    }

    @Test
    void missingRequiredQueryVariableProducesErrors() {
        tester.document("""
                query FindBook($id: ID!) {
                  book(id: $id) { id }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> {
                    assertFalse(errors.isEmpty());
                    errors.forEach(error ->
                            assertNotNull(error.getMessage()));
                });
    }

    @Test
    void missingRequiredMutationVariableProducesErrors() {
        tester.documentName("addBook")
                .execute()
                .errors()
                .satisfy(errors ->
                        assertFalse(errors.isEmpty()));
    }

    @Test
    void invalidSelectionIsCaughtByGraphQlValidation() {
        tester.document("""
                query Broken {
                  book(id: "b1") {
                    fieldThatDoesNotExist
                  }
                }
                """)
                .execute()
                .errors()
                .expect(error ->
                        error.getMessage() != null
                                && !error.getMessage().isBlank())
                .verify();
    }
}
~~~

### Reading the slice test assertions

This class has **11 `@Test` methods**, each exercising one scenario.

| Method | Objective |
| --- | --- |
| `queryUsesNamedDocumentAndIdVariable` | Load `bookById.graphql` and pass `id` |
| `queryChecksMultipleSelectedFields` | Assert three fields from a **single execute** |
| `queryMissingBookReturnsNullNotError` | Distinguish nullable Book from GraphQL errors |
| `queryListChecksValuesAndOrdering` | Verify list values and service-defined ordering |
| `queryCanUseVariablesMap` | `variables(Map)` API for requests |
| `mutationAcceptsInputObjectVariable` | Bind Map into GraphQL `BookInput!` |
| `mutationChangesStateVisibleToNextQuery` | Mutation causes real side effect visible to next query |
| `mutationResultHasAllExpectedFields` | Assert ID, title, and pages of mutation response |
| `missingRequiredQueryVariableProducesErrors` | Omitted non-null `ID!` |
| `missingRequiredMutationVariableProducesErrors` | Omitted non-null `BookInput!` |
| `invalidSelectionIsCaughtByGraphQlValidation` | Field outside schema rejected by GraphQL validation |

**Why is this test called a slice?** `@GraphQlTest` loads GraphQL infrastructure and the specified controller without starting an HTTP server. `@Import(BookCatalog.class)` brings the real service into the slice. We verify the schema, argument binding, query/mutation resolvers, and GraphQL response shape. However, this test does not prove that the `POST /graphql` network endpoint works or that security filters allow HTTP requests.

### Why reset before and after each test?

`BookCatalog` holds data inside a singleton bean. A mutation test adds `b3` to the map; without a reset, a subsequent test expecting only `b1` and `b2` can fail depending on execution order. `@BeforeEach` prepares the fixture, and `@AfterEach` cleans up state even if an assertion throws a normal exception. In a real project, state may reside in a DB, cache, queue, or external service; apply matching cleanup.

**Do not enable parallel test execution on the same mutable context** without isolation: `reset()` in test A can wipe data that test B is checking. To run in parallel, use per-test catalogs/contexts, test run IDs, separate databases/schemas, or concurrency-safe fixtures.

## 9. HTTP integration: `HttpGraphQlTester` over a real server

To test the HTTP path, add a separate class. In Spring Boot 3.3, when `@SpringBootTest(webEnvironment = RANDOM_PORT)` starts the server and appropriate dependencies are present, Boot configures `HttpGraphQlTester` for the live server. With a Spring MVC demo plus test-scoped WebFlux client, the tester sends GraphQL requests over HTTP.

**`src/test/java/com/example/graphql/BookGraphQlHttpTest.java`**:

~~~java
package com.example.graphql;

import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        classes = GraphQlApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BookGraphQlHttpTest {

    @Autowired
    private HttpGraphQlTester tester;

    @Autowired
    private BookCatalog catalog;

    @BeforeEach
    void setUp() {
        catalog.reset();
    }

    @AfterEach
    void cleanUp() {
        catalog.reset();
    }

    @Test
    void queryRunsOverRealHttpTransport() {
        tester.documentName("bookById")
                .variable("id", "b1")
                .execute()
                .path("book.title")
                .entity(String.class)
                .isEqualTo("Java 17");
    }

    @Test
    void mutationRunsOverHttpAndUpdatesState() {
        String id = tester.documentName("addBook")
                .variable("input", Map.of(
                        "title", "HTTP GraphQL",
                        "pages", 190))
                .execute()
                .path("addBook.id")
                .entity(String.class)
                .get();

        assertNotNull(id);

        tester.documentName("bookById")
                .variable("id", id)
                .execute()
                .path("book.title")
                .entity(String.class)
                .isEqualTo("HTTP GraphQL");
    }

    @Test
    void listQueryWorksOverHttp() {
        tester.document("{ books { title } }")
                .execute()
                .path("books[*].title")
                .entityList(String.class)
                .hasSize(2);
    }
}
~~~

These are **3 `@Test` methods**. `HttpGraphQlTester` preserves the same `document/variable/execute/path` syntax as the slice test, while adding HTTP transport. It verifies that the Spring Boot endpoint is listening and accepting GraphQL requests, performing JSON serialization/deserialization, and routing as currently configured.

### Limitations of this HTTP test

- No Spring Security dependency, so authorization and authentication are not checked.
- No DB or transactions, so only in-memory mutations and state on the same app instance are verified.
- No proxy/API gateway/CDN, so production network configuration is not tested.
- No subscriptions; this article focuses on queries, mutations, and variables.
- No load/concurrency testing or query complexity limits.
- Does not assert custom low-level status codes or headers since the primary focus is GraphQL semantics. For auth, cookies, correlation IDs, or HTTP response headers, use an appropriate transport client and HTTP-level assertions.
- No DELETE API, so in-memory mutation cleanup uses `catalog.reset()`; with a committed DB, do not assume a test-thread rollback deletes server-committed data.

To customize headers per tester, `HttpGraphQlTester` can mutate the WebTestClient configuration. When the app has authentication, build dedicated testers with explicit test credentials and test both valid and invalid cases in the proper environment.

## 10. Running Gradle and reading results

From the root directory containing `gradlew`/`gradlew.bat`:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run only the GraphQL slice:

~~~bash
./gradlew test --tests 'com.example.graphql.BookGraphQlSliceTest'
~~~

Run only HTTP integration:

~~~bash
./gradlew test --tests 'com.example.graphql.BookGraphQlHttpTest'
~~~

With these two classes, there are **11 + 3 = 14 `@Test` methods**, one invocation each. With matching versions, dependencies, schema, and demo code, **14 tests are expected to pass**. This is an **expected outcome from the source**, not an actual test run log inside the learner's repository.

Standard Gradle/JUnit reports are written to:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.graphql.BookGraphQlSliceTest.xml
    └── TEST-com.example.graphql.BookGraphQlHttpTest.xml
~~~

The tests do not call `System.out.println`, so **there is no fixed business stdout**. Gradle reports `BUILD SUCCESSFUL` when all tasks succeed; reruns may report `UP-TO-DATE` or `FROM-CACHE`. When you need to force re-execution for diagnostics:

~~~bash
./gradlew test --rerun-tasks
~~~

If a new project has no Wrapper yet, a compatible Gradle installation is needed to bootstrap it, for example:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Then keep the scripts, Wrapper JAR, and `gradle-wrapper.properties` in the repository. Real projects should use the Gradle Wrapper standardized by the team rather than changing versions arbitrarily per lesson. The Java toolchain requires JDK 17 available or an appropriate provisioning setup.

### Trying with curl to understand the HTTP payload

After starting the app with `./gradlew bootRun` on a local machine where port 8080 is free (or configuring a different `server.port`), query:

~~~bash
curl -i http://localhost:8080/graphql \
  -H 'Content-Type: application/json' \
  -d '{"query":"query FindBook($id: ID!) { book(id: $id) { id title } }","variables":{"id":"b1"}}'
~~~

This command is formatted for Linux/macOS shells. In Windows PowerShell, escaping/quoting rules differ; you can send an equivalent request via Postman or client code. Real projects should not depend on port 8080 in integration tests: `HttpGraphQlTester` with `RANDOM_PORT` binds to the runtime port automatically, avoiding conflicts.

Mutation via raw HTTP JSON:

~~~bash
curl -i http://localhost:8080/graphql \
  -H 'Content-Type: application/json' \
  -d '{"query":"mutation Add($input: BookInput!) { addBook(input: $input) { id title pages } }","variables":{"input":{"title":"HTTP Book","pages":120}}}'
~~~

If the mutation succeeds, the response includes the corresponding `data.addBook`. The in-memory demo generates ID `b3` for the first mutation after reset or service startup. However, if a book was created earlier via curl, the next ID **is not fixed**; tests should not hardcode IDs against a long-lived stateful server.

## 11. Distinguishing GraphQL variables from resolver arguments

Document:

~~~graphql
query FindBook($id: ID!) {
  book(id: $id) {
    title
  }
}
~~~

There are two `id` symbols:

- `$id` is the **GraphQL variable** sent by the client in `variables`.
- `book(id: ...)` is the **GraphQL field argument** defined in the schema.
- `@Argument("id")` is how Spring GraphQL passes the field argument value into the Java parameter.
- `BookCatalog.findById(id)` is the application logic.

Data flow:

~~~text
Java test .variable("id", "b1")
       |
       v
GraphQL request variables: {"id":"b1"}
       |
       v
GraphQL variable coercion against ID!
       |
       v
Schema field Query.book(id: ID!)
       |
       v
@QueryMapping book(@Argument("id") String id)
       |
       v
BookCatalog.findById("b1")
       |
       v
GraphQL data.book.title
       |
       v
GraphQlTester.path("book.title").entity(String.class)
~~~

If the variable name differs from the argument name, there is no issue as long as the document maps them correctly:

~~~graphql
query Lookup($requestedId: ID!) {
  book(id: $requestedId) {
    title
  }
}
~~~

Here the test passes `variable("requestedId", "b1")`, while the resolver keeps `@Argument("id")`. Do not change the Java annotation to match the **client's variable name**; the Java annotation corresponds to the **schema field argument**.

## 12. Mutations: verify side effects, not just the response

A mutation can return:

~~~json
{
  "data": {
    "addBook": {
      "id": "b3",
      "title": "HTTP GraphQL",
      "pages": 190
    }
  }
}
~~~

Yet if the controller merely constructs a DTO and **does not persist it**, a test checking only `addBook.title` still passes. For state-changing mutations, follow these steps:

1. Execute the mutation with valid input variables.
2. Assert the response ID, fields, and validation per the contract.
3. Run a **follow-up query** or a repository read in a separate transaction to verify the side effect.
4. Clean up created test data afterward without relying on other tests.
5. If the mutation is asynchronous, use bounded polling for eventual state instead of arbitrary sleeps.

The demo project includes `mutationChangesStateVisibleToNextQuery` and `mutationRunsOverHttpAndUpdatesState`. Both execute a **query after the mutation** to verify state.

### When a mutation uses a DB transaction

`@SpringBootTest(RANDOM_PORT)` sends real HTTP traffic from the test thread to the server thread. If a mutation writes to a database using `@Transactional` on the service, the server-side transaction **commits independently** before the response returns. `@Transactional` on the JUnit test method does not roll back server-side commits. Clean up using IDs/test markers in an independent transaction, a DELETE API, or an isolated DB/schema/container. **Do not apply the demo's in-memory reset directly to a production PostgreSQL database.**

### Can a mutation return partial data and errors?

Yes. A mutation can touch multiple resolvers/fields, and a failure on one field after the mutation does not automatically roll back everything already written. The GraphQL response contract **does not automatically equal transaction semantics**. Tests must define idempotency, atomicity, compensation, and recovery appropriate for the domain, especially when mutations publish messages or call external services.

## 13. `null` fields and GraphQL non-null propagation

The `!` in a GraphQL schema applies to both arguments and outputs:

~~~graphql
type Book {
  id: ID!
  title: String!
  pages: Int!
}
~~~

If a resolver returns `null` for `Book.title` even though the schema says `String!`, GraphQL execution treats it as a non-null error. Under propagation rules, null can bubble up to the parent field, or even to `data`, depending on the non-null chain in the schema.

This differs from `book(id: ID!): Book` (nullable): **not finding a book** can return `book: null` **with no error**, just as in the demo.

| Scenario | Expected assertion to check |
| --- | --- |
| Valid ID and book exists | `path("book.title").entity(String.class).isEqualTo(...)` |
| Valid ID but not found | `path("book").valueIsNull()` if schema/contract allows |
| Missing `ID!` | Non-empty `errors()`, do not expect resolver success |
| Non-existent selected field | GraphQL validation error |
| Non-null output field returns null | GraphQL execution error and null propagation |
| Document omits `pages` field | `pages` is absent from data selection; do not infer pages is null in DB |

A good test does not try to match the entire JSON body when the schema permits varying field selections. Check the exact part of the response requested by the client.

## 14. Query documents and fragments in large test suites

When tests repeatedly select the same fields, fragments keep selection sets consistent:

~~~graphql
fragment BookFields on Book {
  id
  title
  pages
}
~~~

Document using the fragment:

~~~graphql
query FindBook($id: ID!) {
  book(id: $id) {
    ...BookFields
  }
}
~~~

If the fragment is stored in a separate file under `graphql-test/`, Spring `GraphQlTester` supports APIs such as `fragmentName("bookFields")` to include the fragment during execution per document source configuration. Illustrative example:

~~~java
tester.documentName("bookByIdWithFragment")
        .fragmentName("bookFields")
        .variable("id", "b1")
        .execute()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Java 17");
~~~

**This is an extended snippet**, not part of the runnable project because the two resources `bookByIdWithFragment.graphql` and `bookFields.graphql` were not created. The GraphQL operation must be valid after fragments are merged; duplicate fragment names or mismatched type conditions cause GraphQL validation errors.

When a document contains **multiple operations**, such as a query and a mutation in the same file, the client must choose the operation using `operationName`. In the demo project, each document has a single operation, so `operationName` is omitted. In test suites sharing files with different operation names, specifying `operationName` explicitly helps reviewers see which branch a call executes.

## 15. Authentication, HTTP headers, and GraphQlTester

GraphQL path assertions are no substitute for authentication/authorization tests. There are three easily confused levels:

- `@GraphQlTest`: tests server-side resolvers/schema and may bypass HTTP security filters.
- `HttpGraphQlTester` over a mock web environment: may exercise part of the web stack as configured in the context.
- `HttpGraphQlTester` over a real HTTP server: tests routing and filters/headers/auth in that environment, though still without production proxies/gateways.

With Boot 3.3, you can derive a tester variant via `HttpGraphQlTester.mutate()` to configure `WebTestClient` headers, for example:

~~~java
HttpGraphQlTester authenticated = tester.mutate()
        .webTestClient(builder ->
                builder.defaultHeaders(headers ->
                        headers.setBearerAuth("test-token")))
        .build();

authenticated.document("{ books { id } }")
        .execute()
        .path("books[*].id")
        .entityList(String.class)
        .hasSize(2);
~~~

This is an **illustrative snippet** for an environment with security configured and a valid test token; the runnable project does not use Spring Security, and `test-token` does not represent a real credential. Do not hardcode production tokens in tests. To verify 401/403/CSRF/CORS, test directly at the HTTP level or use appropriate security fixtures.

A `DataFetcherExceptionResolver` can map access-denied failures to GraphQL `errors` instead of HTTP 403; establish a clear contract between the HTTP transport and the GraphQL payload. Do not expect every authorization error to return the same HTTP status across all transports.

## 16. Stability and isolation when running mutation tests

A `GraphQlTester` instance does not necessarily spin up a fresh application context per request. `@GraphQlTest` classes may share a cached Spring context; `@SpringBootTest` HTTP tests may share another application context. If a service holds mutable state, a mutation in one test can affect a query in a subsequent test.

### Isolation pattern in the demo

~~~java
@BeforeEach
void setUp() {
    catalog.reset();
}

@AfterEach
void cleanUp() {
    catalog.reset();
}
~~~

Goal: every test method starts with `b1`/`b2` and prevents `b3` from leaking into the next method. However, this approach only works for **tests that do not run in parallel against the same mutable singleton**. For parallel execution:

- Use separate catalog instances per test or proper context isolation;
- Use distinct namespaces/testRunIds to partition state;
- Use separate DBs/schemas per job or test class;
- Or configure state-mutating tests not to run concurrently.

### Do not use `@DirtiesContext` for every mutation

`@DirtiesContext` evicts the context from the Spring TestContext cache, forcing context reinitialization. While it may be needed when a stateful bean cannot be reset, it **does not roll back server-side DB commits** or undo side effects outside the JVM. For an in-memory demo, resetting the fixture is sufficient and much faster. For real storage, apply appropriate cleanup.

### Never call `deleteAll()` on a shared DB

If `BookCatalog` is later replaced by a JPA repository, cleanup like `repository.deleteAll()` can wipe another test's data or shared data. Create books with a test marker, track IDs, and delete only the created records; in critical environments, provision dedicated schemas or containers. If mutations produce outbox messages, caches, or uploaded files, cleanup must cover those side effects too.

## 17. Common errors and troubleshooting

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `NoSuchBeanDefinitionException: GraphQlTester` | Missing `spring-graphql-test` or test context does not auto-configure tester | Add the proper test dependency, use `@GraphQlTest` or configure tester explicitly |
| `Failed to load ApplicationContext` in `@GraphQlTest` | Resolver needs a service not in the slice | Use `@Import` or `@MockBean` intentionally; inspect root cause |
| `field undefined` in GraphQL | Schema lacks field or selection is wrong | Cross-check `schema.graphqls` against document |
| `Variable ... was not provided` | Missing non-null variable or wrong variable name | Pass `variable("id", value)` properly; distinguish variable vs argument |
| Input object does not bind to record | Wrong field name/type, schema mismatches Java | Check `BookInput` fields, `@Argument("input")`, nullability |
| Query returns null when test expects data | Missing record, wrong ID, or resolver returns null | Check fixture and data path; do not equate null with an error |
| Test only checks HTTP 200 but errors occur | GraphQL `errors` in response | Use `GraphQlTester.errors()` and assert data/errors per contract |
| `path("data.book.title")` not found | `GraphQlTester` path is relative to `data` | Use `path("book.title")` |
| `entity(Integer.class)` type mismatch | GraphQL scalar/JSON decoding mismatch | Match Java type; do not coerce String into Int |
| `containsExactly` fails intermittently | Backend list has no guaranteed order | Sort in resolver or use an order-independent assertion |
| Mutation test passes but DB lacks data | Only asserted response, skipped side-effect check | Run follow-up query/repository read after mutation |
| Subsequent test sees book created by prior test | Singleton state/cache not reset | `@BeforeEach`/`@AfterEach`, namespace, or isolation |
| HTTP tester connects to wrong port | Hardcoded 8080 instead of `RANDOM_PORT` | Use Boot auto-configured tester or runtime base URL |
| `HttpGraphQlTester` fails to autowire | Missing HTTP client test support or wrong boot context | Include `spring-graphql-test` and test-scoped `spring-boot-starter-webflux` in Boot 3.3 |
| GraphQL error message changes | Test asserts exact internal wording | Check stable type/code/semantics |
| 401/403 even though GraphQL query is valid | HTTP filter/auth blocks before resolver | Use test security fixtures and a tester with credentials |
| `@GraphQlTest` passes, HTTP API broken | Slice does not test network/filters | Add HTTP integration test with `HttpGraphQlTester` |
| Test gets no data from `documentName` file | File in wrong folder/extension/name | Place under `src/test/resources/graphql-test/` |
| `@MockBean` API unavailable in newer Boot | Code snippet from a different major version | Use the mock annotation matching your Boot/Spring Framework version |
| Complex/malicious query overloads server | No complexity/depth limit, resolver N+1 | Configure limits, DataLoader, auth, and performance tests |
| Mutation returns error yet persists data | No transaction/compensation or post-commit error | Verify actual side-effect and rollback semantics |

### Layered diagnosis

1. **Classpath:** are `spring-boot-starter-graphql`, `spring-graphql-test`, JUnit, and the proper transport client present?
2. **Schema:** were `*.graphqls` files loaded? Are type/field/argument names exact?
3. **Resolvers:** is `@Controller` scanned? Do `@QueryMapping`/`@MutationMapping` match the schema?
4. **Variables:** names have `$` in the document but **no `$`** in `variable("id", ...)`; are `ID!`, `Int!`, `BookInput!` types valid?
5. **Response:** inspect both `data` and `errors`, not just HTTP status.
6. **Path:** `path` is relative to `data`; do lists have correct JSONPath/ordering?
7. **State:** do mutation tests have isolated fixtures and cleanup?
8. **Transport:** slice or real HTTP? If headers/auth/port fail, check `HttpGraphQlTester` and networking.
9. **Root cause:** read sanitized stack traces/application logs without exposing credentials or real user data.

## 18. GraphQlTester scope compared to SOAP testing

Because the parent topic is **GraphQL and SOAP**, keep the boundary clear:

| GraphQL | SOAP |
| --- | --- |
| GraphQL schema `type Query`, `type Mutation`, `input` | WSDL, XSD, and SOAP envelope |
| `GraphQlTester.document(...).variable(...)` | SOAP client/endpoint testers for Spring Web Services |
| Response `data` and `errors` | SOAP Body/Header and Fault |
| Selection sets, arguments, GraphQL validation | XML namespaces, SOAPAction, XSD validation |
| `@QueryMapping`, `@MutationMapping` | `@Endpoint`, `@PayloadRoot` in Spring-WS |
| HTTP POST `/graphql` or other GraphQL transport | SOAP over HTTP or corresponding transport |

`GraphQlTester` is **not** designed to test SOAP envelopes, XPath in XML, WS-Security, or WSDL contracts. When teaching or writing SOAP tests, use SOAP-specific testing APIs and XML/SOAP rules rather than `GraphQlTester` just because both can run over HTTP.

## 19. Hands-on exercises

**Exercise A — required ID variable:** Send `bookById.graphql` with `id=b2` and assert title `Spring Boot`. Omit the `id` variable and assert `errors` is non-empty. Explain why `ID!` rejects the request before the resolver.

**Exercise B — null vs error:** Send `id=missing` and assert `path("book").valueIsNull()` with no GraphQL validation error. Temporarily change the schema `book` field to non-null and analyze the impact when the resolver returns null.

**Exercise C — input object mutation:** Create a book with `title="GraphQL Practice"`, `pages=95` via `variable("input", Map.of(...))`. Assert the response, then query by the created ID to verify state.

**Exercise D — renaming a variable:** Change the document from `$id` to `$bookId`, keeping argument `book(id: $bookId)`. Update the test to `variable("bookId","b1")`. Explain why the Java controller still keeps `@Argument("id")`.

**Exercise E — list ordering:** Intentionally reverse sorting in `BookCatalog.findAll()` and run `containsExactly`. The test must fail when order is part of the contract. If the product does not require ordering, redesign the test as an unordered set check or add `orderBy` to the schema.

**Exercise F — operation selection:** Create a document containing two queries named `FindBook` and `AllBooks`. Use `operationName("FindBook")` to choose the right operation; observe what happens if `operationName` is omitted in a multi-operation request.

**Exercise G — field error:** Query a non-existent field and use `errors().expect(...)` or `satisfy(...)` to assert the validation error. Do not ignore errors with a global `errorFilter(error -> true)`.

**Exercise H — business error mapping:** When `pages=0`, the service throws `IllegalArgumentException`. Add a `DataFetcherExceptionResolver` or `@GraphQlExceptionHandler` for your version, mapping it to a contract GraphQL error code. Test the stable code/message without asserting a verbatim stack trace.

**Exercise I — HTTP and security:** Add Spring Security, requiring a Bearer token for mutations while allowing appropriate queries. Test unauthorized and authorized calls through an HTTP tester with headers. Do not use production tokens.

**Exercise J — real persistence:** Replace the in-memory service with Spring Data JPA and Testcontainers PostgreSQL. Use `@SpringBootTest(RANDOM_PORT)` to run a mutation followed by a query; clean up by ID in a separate transaction. Do not assume a test-thread rollback reverts server commits.

## 20. Pre-merge checklist for GraphQL tests

- [ ] Do I know the exact GraphQL schema and field/argument names?
- [ ] Does the document specify the right query/mutation, selection set, and `operationName` when needed?
- [ ] Are variables passed via `variable`/`variables` instead of concatenating raw user text into the document?
- [ ] Do scalar types (`ID!`, `String!`, `Int!`) and input objects (`BookInput!`) match?
- [ ] Do query tests check valid data, null when missing, and lists/ordering when relevant?
- [ ] Do mutation tests verify **both the response and side effects**, not just the payload?
- [ ] Are `GraphQlTester` paths relative to `data` without a redundant `data.` prefix?
- [ ] Have I separated `GraphQL errors` from HTTP status/header errors?
- [ ] Do error tests use `expect`/`satisfy` rather than filtering out all errors to keep tests green?
- [ ] Did I choose `@GraphQlTest` vs `@SpringBootTest` appropriately for the transport target?
- [ ] Are `spring-graphql-test` and `WebTestClient` support present when using `HttpGraphQlTester`?
- [ ] Are controller service dependencies properly imported or mocked within the slice?
- [ ] Are mutation tests isolated, resetting fixtures or cleaning up committed DB data?
- [ ] Do tests avoid relying on shared mutable state when running in parallel?
- [ ] Do tests avoid leaking tokens, customer info, or production connections?
- [ ] When testing SOAP, am I using SOAP tools instead of mistakenly using `GraphQlTester`?
- [ ] Do Gradle/JUnit reports confirm that all test methods actually executed?

## 21. Official references

Reference documentation for **Spring Boot 3.3.x / Spring for GraphQL 1.3.x** used in the example. Newer Boot/Spring GraphQL lines may change packages, default test infrastructure, and mock annotations; always check the Javadoc for the version you are running.

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@GraphQlTest`, test slices, `ExecutionGraphQlServiceTester`, and `HttpGraphQlTester`.
- [Spring for GraphQL — Testing Reference](https://docs.spring.io/spring-graphql/reference/testing.html): request documents, variables, error assertions, tester variants.
- [Spring for GraphQL 1.3 — GraphQlTester API](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/test/tester/GraphQlTester.html): `documentName`, `variable`, `variables`, `execute`, `path`, `errors`.
- [Spring for GraphQL 1.3 — GraphQlTester.Path API](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/test/tester/GraphQlTester.Path.html): `hasValue`, `valueIsNull`, `entity`, `entityList`.
- [Spring — Building a GraphQL Service](https://spring.io/guides/gs/graphql-server): schema, controller mapping, queries, and slice `GraphQlTester`.
- [GraphQL Specification](https://spec.graphql.org/October2021/): operations, selection sets, variables, non-null, input coercion, and response errors.

**Key takeaway:** `GraphQlTester` tests **GraphQL documents + variables + data/errors** with one consistent API regardless of whether the tester runs server-side or over HTTP. Use `@GraphQlTest` for fast query/mutation resolver tests, `HttpGraphQlTester` when verifying HTTP transport, and always confirm mutations changed state as expected. A test that only sees HTTP 200 or only checks `data.addBook.title` **is not sufficient proof** of the system's GraphQL behavior.