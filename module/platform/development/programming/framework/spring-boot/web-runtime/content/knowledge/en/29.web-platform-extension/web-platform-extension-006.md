# Boundaries Between the HTTP Runtime and GraphQL Schema, Resolvers, and Data Models in Spring Boot

## 1. Goal: Understand the Four Layers Before Writing a GraphQL API

A single Spring Boot web application can expose REST, GraphQL, WebSocket, and other endpoints on the same embedded HTTP server. With REST, developers are used to `@GetMapping("/books/{id}")` returning a DTO. With GraphQL, applying a "one URL per field" mindset mixes responsibilities: a single controller parses HTTP JSON, checks the schema, queries the database, and decides both response status and data shape. That makes code hard to maintain, test, and secure.

**GraphQL separates work into distinct layers**:

1. **HTTP runtime/transport:** receives HTTP requests, handles TLS, routes `/graphql`, enforces CORS, runs session/security filters, caps request body size, reads headers, and writes responses.
2. **GraphQL schema/contract:** declares the data types and operations/fields clients are **allowed to request**, typically in SDL (`.graphqls`).
3. **GraphQL execution and resolvers/data fetchers:** parses, validates, executes operations, resolves individual fields per schema, coordinates variables/contexts, batches calls, and handles GraphQL errors.
4. **Application service, domain, and data model:** enforces business rules, data access permissions, transactions, persistence, DTOs, and database or external API integration.

This lesson focuses on **boundaries and responsibilities** across those layers rather than teaching every GraphQL syntax feature or replacing dedicated lessons on REST, JPA, and Spring Security. Examples use **Spring Boot 3.3.x, Spring for GraphQL 1.3.x, Spring Framework 6.1.x, and Java 21** (Java 17+ compatible). Properties and packages match the Spring Boot 3.3 generation and should not be mixed with Spring Boot 4.x configs.

**High-level diagram:**

```text
Browser / mobile / GraphQL client
    |
    | POST /graphql
    | {"query": "...", "variables": {...}}
    v
HTTP runtime: Tomcat + Spring MVC / Reactor Netty + WebFlux
    | TLS, CORS, auth, HTTP parsing, routing, request size
    v
GraphQL web transport: WebGraphQlHandler / interceptors
    | GraphQL request object, GraphQL context, response metadata
    v
ExecutionGraphQlService + GraphQlSource
    | GraphQL Java: parse -> validate -> select operation -> execute fields
    v
Data fetchers: @QueryMapping / @MutationMapping / @SchemaMapping
    | fetch fields, bind arguments, data loaders, authorization
    v
Application services -> domain rules -> repositories / remote APIs
    |
    v
GraphQL ExecutionResult: data, errors, extensions
    |
    v
HTTP response (typically JSON; HTTP status depends on transport/error)
```

**Most important distinction:** `@QueryMapping` is a **field resolver for `Query` in the schema**, not an HTTP `@GetMapping`. A GraphQL schema **is not** a JPA entity schema. And HTTP status `200` **does not prove** every GraphQL field succeeded.

## 2. Why GraphQL Is Not Just Another REST HTTP Endpoint

In REST, URLs typically represent resources or actions:

```http
GET /api/books/b1
GET /api/books/b1/author
POST /api/books
```

In GraphQL, many queries and mutations are sent to **one HTTP endpoint** such as `/graphql`; the request body specifies the operation and desired fields:

```http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "query": "query GetBook($id: ID!) { book(id: $id) { id title author { name } } }",
  "variables": {"id": "b1"},
  "operationName": "GetBook"
}
```

The client does not call a separate URL for `author.name`. The GraphQL engine resolves `book`, then `author`, then `name` based on the **schema, runtime wiring, and returned data**. The shape of `data` in the response mirrors the client's selection set.

Illustrative response:

```json
{
  "data": {
    "book": {
      "id": "b1",
      "title": "Spring Boot",
      "author": {
        "name": "Lan"
      }
    }
  }
}
```

If the client requests only `book { title }`, the response omits `author`, unlike a REST DTO returning all fields. **The schema constrains structural queryability**, yet **does not constrain access to specific records** — that authorization belongs in the business/resolver layer.

Fundamentally, GraphQL **does not require HTTP**: the engine and schema can be invoked over WebSocket, RSocket, or directly in tests. HTTP is simply one common transport.

## 3. Responsibility Map to Avoid Mixing Layers

| Question | Primary Responsible Layer | Example |
| --- | --- | --- |
| Which port receives requests, and is TLS active? | HTTP runtime and infrastructure | `server.port`, `server.ssl.*`, reverse proxy |
| What is the GraphQL HTTP endpoint path? | Spring Boot GraphQL transport | `spring.graphql.path=/graphql` |
| Which browser origins may send/read requests? | HTTP/gateway CORS & security | `spring.graphql.cors.*` |
| Does the HTTP request carry valid JSON? | Transport/codec | `Content-Type: application/json` |
| Does `book(id: ID!)` exist? | GraphQL schema and validation | SDL type `Query` |
| Is requesting `Book.secretField` valid? | GraphQL validation | Undefined field → validation error |
| Where is `book` loaded from? | Resolver + service/repository | `@QueryMapping` calling `BookCatalog` |
| How is `Book`'s `author` fetched? | Field resolver/batch loader | `@SchemaMapping` or `@BatchMapping` |
| Who may view this book? | Business authorization | Owner/tenant/ACL check |
| How is `BookView` DTO built? | Service/DTO mapping | Domain → API view |
| Which fields may be `null`? | GraphQL schema, resolver contract | `Book!`, `[Book!]!` |
| One field fails while another succeeds? | GraphQL execution/error handling | Partial `data` + `errors` |
| How to prevent N+1 queries? | Resolver/data loader/repository | `@BatchMapping`, batch fetch |
| Mutation transactions? | Application service/data access | `@Transactional` at the right boundary |
| Which HTTP status on transport errors? | Web transport/GraphQL-over-HTTP policy | 400/401/403/500/2xx depending on situation |

Never write a `@RestController` that manually unpacks `{query: ...}` and blindly assigns HTTP `200` to every error. With Spring for GraphQL, the framework supplies the web adapter and execution service; the app supplies schemas, resolvers, and business services.

## 4. How Spring Boot 3.3 Connects the GraphQL Engine to HTTP

Spring Boot auto-configuration requires **at minimum**:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-graphql'
```

This starter brings in Spring GraphQL/GraphQL Java, and to accept HTTP requests you add a web transport:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
```

or:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-webflux'
```

Spring MVC uses the Servlet stack (typically embedded Tomcat); WebFlux typically uses Reactor Netty. In Spring Boot, the **default GraphQL HTTP POST endpoint is `/graphql`**, exposed via a `RouterFunction` bean with documented ordering rather than a developer-written `@PostMapping` method. Be mindful of this when adding custom `RouterFunction` beans on overlapping routes.

Spring Boot auto-configures:

- `GraphQlSource` to construct the `graphql.GraphQL` engine.
- Loaders reading SDL schemas from the classpath.
- Annotated controller configurer converting `@QueryMapping`, `@SchemaMapping` into GraphQL Java `DataFetcher`s.
- HTTP transport handler/`ExecutionGraphQlService`.
- `RuntimeWiringConfigurer`, `DataFetcherExceptionResolver`, and instrumentation beans when declared by the app.

The GraphQL **WebSocket endpoint** is not enabled automatically just by having HTTP GraphQL. In Boot 3.3, configure `spring.graphql.websocket.path`; on Servlet you also need the WebSocket starter. WebFlux supports its corresponding transport when configured. SSE subscriptions are supported in recent versions too, yet none of these transports blur the boundary between schema and business data.

## 5. Schema SDL: GraphQL's Contract, Not Java Classes

Schema Definition Language (SDL) declares the operations, types, fields, arguments, and nullability exposed by the GraphQL server. Example:

```graphql
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Mutation {
  addBook(input: NewBookInput!): Book!
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

input NewBookInput {
  title: String!
  authorId: ID!
}
```

Meaning:

- `Query` declares root fields for **reading** data.
- `Mutation` declares root fields that can **mutate** system state.
- `book(id: ID!): Book` returns `Book` or `null`; argument `id` is required.
- `books: [Book!]!` returns a non-null list whose elements are each non-null. An empty list `[]` is still valid.
- `Book.author: Author!` promises the `author` field will not be `null` when its parent `Book` exists; if the resolver breaks that promise, **null propagation** and GraphQL errors occur.
- `input NewBookInput` is a **distinct input type**, not the output object `Book`. GraphQL separates input types from output object types.

The schema says nothing about **whether `Book` is stored in Postgres, MongoDB, or a remote API**, which Java entities back it, or any SQL query. It is strictly **the data contract used by the GraphQL engine to validate and execute**.

`ID` in SDL is a **GraphQL identifier scalar**, typically serialized as a JSON string. It does not mandate a `long` database primary key, grant authorization, or guarantee UUID format. `String!` enforces non-null at the GraphQL layer, while business logic still validates length, characters, and domain rules.

## 6. Schema File Locations and Boot 3.3 Configuration

In Spring Boot 3.3, `.graphqls` or `.gqls` schemas under `src/main/resources/graphql/` are auto-discovered. Example:

```text
src/main/resources/graphql/
    catalog.graphqls
```

You can split schemas across multiple files by module, provided all final merged/parsed type and field definitions remain **valid and consistent**. Wrong directory paths or extensions prevent Boot from loading the schema as intended.

Related configuration:

```properties
spring.graphql.path=/graphql

# Default conventions: schemas under classpath graphql directory.
# spring.graphql.schema.locations=classpath:graphql/
# spring.graphql.schema.file-extensions=.graphqls,.gqls

# Dev-only convenience; default disabled in typical production.
spring.graphql.graphiql.enabled=false
spring.graphql.schema.printer.enabled=false
```

If schemas are packaged across multiple modules/JARs, Spring Boot supports classpath resource patterns for `locations`. Do not assume `.graphql` files in source are picked up automatically: client/test query documents often use `.graphql`, while Spring Boot schemas default to `.graphqls`/`.gqls`.

`spring.graphql.schema.introspection.enabled=false` can restrict introspection for operational policy, yet **it is not a security layer replacing authorization**. Clients can still query known field names. GraphiQL and schema printer are separate utilities that should be enabled strictly per environment.

**Version warning:** In Spring Boot 3.3, the HTTP route property is `spring.graphql.path`. Newer Boot releases may reorganize HTTP transport properties; do not copy Boot 4.x property names into a 3.3 app.

## 7. Resolvers Are Field Functions, Not HTTP Controller Endpoints

Spring for GraphQL provides annotated controllers:

```java
@Controller
class GreetingGraphQlController {

    @QueryMapping
    String greeting(@Argument String name) {
        return "Hello, " + name;
    }
}
```

This is an **integration code snippet** requiring a matching schema like `type Query { greeting(name: String!): String! }`, Spring imports, and package scanning via `@SpringBootApplication`. `@QueryMapping` maps the method to `Query.greeting`; Spring converts it into a **GraphQL Java `DataFetcher`**.

Use `@Controller`; there is no need for `@RestController` or `@PostMapping("/graphql")`. `@RestController` targets Spring MVC HTTP handler methods and plays no required role in registering GraphQL annotated methods.

Primary annotations:

| Annotation | Maps to Schema | Role |
| --- | --- | --- |
| `@QueryMapping` | `Query.someField` | Root query resolver |
| `@MutationMapping` | `Mutation.someField` | Root mutation resolver |
| `@SubscriptionMapping` | `Subscription.someField` | Root subscription resolver |
| `@SchemaMapping` | `TypeName.fieldName` | Resolver for any object type field |
| `@Argument` | Field GraphQL argument | Binds scalar/input object to Java parameter |
| `@BatchMapping` | Field needing batch loading | Batching to reduce N+1 |
| `@ContextValue` | `GraphQLContext` | Per-request metadata, not raw HTTP |
| `@GraphQlExceptionHandler` | Data-fetching exceptions | Maps errors into GraphQL errors per policy |

`@SchemaMapping(typeName="Book",field="author")` does not create a route `/graphql/book/author`. It runs only after **a GraphQL operation validates** and execution reaches the requested `Book.author` field.

## 8. Execution Path of a Nested Query

Suppose a client sends:

```graphql
query {
  book(id: "b1") {
    id
    title
    author {
      id
      name
    }
  }
}
```

Conceptually, the GraphQL engine executes:

```text
(1) Parse GraphQL document
(2) Validate fields/arguments/types against the schema
(3) Resolve root Query.book(id:"b1")
    -> BookGraphQlController.book(...)
    -> BookCatalog.find(...)
    -> BookView("b1", ...)
(4) Resolve Book.id, Book.title
    -> default property fetching from BookView getters
(5) Resolve Book.author
    -> @SchemaMapping("Book","author")
    -> BookCatalog.findAuthor(book.authorId)
(6) Resolve Author.id, Author.name
    -> default property fetching from AuthorView getters
(7) Assemble GraphQL ExecutionResult
(8) Serialize JSON over the HTTP web transport
```

Key takeaway: **you do not need an explicit Java resolver method for every scalar field**. For standard properties like `getId()`, `getTitle()`, and `getName()`, GraphQL Java uses its **default property data fetcher**. For fields requiring joins, lazy loads, or authorization like `Book.author`, a dedicated resolver makes execution explicit.

If the client requests only `book { title }`, the `author` field resolver does not run. Still, do not assume every business/DB step optimizes itself automatically to match the selection set: the root resolver might still fetch extra columns. Deep optimization requires explicit repository projections or batch fetching.

## 9. GraphQL DTOs, Domain Models, and Persistence Entities Can Differ

Consider a book system with three concepts:

```text
Persistence layer
  BookRow(id, title, author_id, internal_cost, deleted_at)
       |
       | mapping + authorization
       v
Domain / application service
  Book business rules: owner, available, canRead...
       |
       | output projection
       v
GraphQL API model
  BookView {id, title, authorId}
       |
       | GraphQL SDL exposes only id, title, author
       v
Client sees Book {id, title, author {id, name}}
```

Domain objects, JPA `@Entity` classes, and GraphQL types do not have to share names or expose identical fields. Separating DTOs helps:

- Avoid leaking internal columns (`passwordHash`, `internalCost`, `tenantId`, soft-delete flags).
- Evolve database structures without breaking the public schema.
- Enforce field-level authorization and data transformations.
- Prevent accidental N+1 queries from JPA lazy relationships.
- Manage nullability cleanly: `Book.author: Author!` must be guaranteed or the schema contract adjusted.

Java `BookView` can carry `getAuthorId()` for resolver use even when the GraphQL SDL **omits** `authorId` from client queries. The GraphQL engine does not expose all Java getters automatically; it resolves only **schema-defined fields** requested in the operation. Still, if the schema exposes a sensitive field matching a getter, enforce authorization — a DTO alone is not complete protection.

## 10. Spring Boot 3.3 Sample Project: Structure and Dependencies

The complete example below uses **Java 21 and Spring Boot 3.3.13** with in-memory data to highlight GraphQL/HTTP boundaries rather than database setup. The consecutive snippets form a runnable Gradle project using the Wrapper, all placed under package `com.example.bookgraphql`.

**Structure:**

```text
build.gradle
src/main/java/com/example/bookgraphql/
  BookGraphQlApplication.java
  BookView.java
  AuthorView.java
  NewBookInput.java
  BookCatalog.java
  BookGraphQlController.java
src/main/resources/
  application.properties
  graphql/catalog.graphqls
src/test/java/com/example/bookgraphql/
  GraphQlSchemaTest.java
  GraphQlHttpTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
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
    // Used to support HTTP GraphQlTester/WebTestClient in tests.
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

- `spring-boot-starter-graphql` provides GraphQL Java and Spring integration.
- `spring-boot-starter-web` provides the Spring MVC Servlet HTTP transport.
- No custom servlet handler is needed to expose `/graphql`.
- `spring-graphql-test` provides `GraphQlTester`.
- WebFlux is in **testImplementation** for the HTTP tester; it does not turn the production MVC app into WebFlux. When both web starters are present at runtime, Boot prioritizes the Servlet application type by default.

This setup is for **learning purposes**, not a recommendation to pin production to an arbitrary patch version; use a BOM and version controlled by your project.

## 11. Real Schema: `src/main/resources/graphql/catalog.graphqls`

```graphql
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Mutation {
  addBook(input: NewBookInput!): Book!
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

input NewBookInput {
  title: String!
  authorId: ID!
}
```

`Query.book` is nullable because failing to find `b1` validly returns `null`. `Mutation.addBook` is non-null, meaning a successful mutation must return a `Book`; on business errors, execution places errors into `errors` per policy and applies null propagation.

Notice the schema **has no `Book.authorId` field**, even though the internal data model stores that foreign key. Clients can only query `author { id name }`. This is an intentional boundary: a **public field** can be resolved from internal data without leaking raw relational columns.

If a client sends `books { costPrice }` when the SDL omits `costPrice`, GraphQL validation rejects the request before any resolver runs. Still, that only blocks undefined fields; for an accessible `Book`, **which records a caller may see** must still be enforced in the service.

## 12. Application Bootstrap and API DTOs: Decoupled from JPA

**`BookGraphQlApplication.java`:**

```java
package com.example.bookgraphql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BookGraphQlApplication {
    public static void main(String[] args) {
        SpringApplication.run(BookGraphQlApplication.class, args);
    }
}
```

**`BookView.java`:**

```java
package com.example.bookgraphql;

import java.util.Objects;

public final class BookView {
    private final String id;
    private final String title;
    private final String authorId;

    public BookView(String id, String title, String authorId) {
        this.id = Objects.requireNonNull(id);
        this.title = Objects.requireNonNull(title);
        this.authorId = Objects.requireNonNull(authorId);
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getAuthorId() {
        return authorId;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof BookView book && id.equals(book.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }
}
```

`BookView` retains `authorId` for resolver implementations, yet the GraphQL schema publishes only `Book.id`, `Book.title`, and `Book.author`. `equals`/`hashCode` based on `id` is convenient if you later use `@BatchMapping` with `BookView` as a map key; only do this when the ID is immutable and uniquely identifies the entity (in multi-tenant systems, include `tenantId + id`).

**`AuthorView.java`:**

```java
package com.example.bookgraphql;

import java.util.Objects;

public final class AuthorView {
    private final String id;
    private final String name;

    public AuthorView(String id, String name) {
        this.id = Objects.requireNonNull(id);
        this.name = Objects.requireNonNull(name);
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

GraphQL Java's default property fetching reads JavaBean getters `getId`, `getTitle`, and `getName` when resolving scalar fields defined in the schema. Thus the demo needs no explicit Java resolvers for `Book.id`, `Book.title`, or `Author.name`.

**`NewBookInput.java`:**

```java
package com.example.bookgraphql;

public record NewBookInput(String title, String authorId) {
}
```

A Java 17+ record acts as the input DTO. Spring GraphQL's `@Argument` binds the GraphQL input object to the primary data constructor (the record's canonical constructor). An input type is not an entity; the application service validates its contents and manages storage.

## 13. Business Service: `BookCatalog.java`

This layer knows nothing about HTTP bodies, `GraphQLContext`, `@SchemaMapping`, or GraphQL selection sets. Its operations can be reused from REST, message consumers, or batch jobs.

```java
package com.example.bookgraphql;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;

@Service
public class BookCatalog {
    private record StoredBook(
            String id, String title, String authorId) {
    }

    private final ConcurrentMap<String, StoredBook> store =
            new ConcurrentHashMap<>();

    private final Map<String, AuthorView> authors = Map.of(
            "a1", new AuthorView("a1", "Lan"),
            "a2", new AuthorView("a2", "Minh"));

    private final AtomicInteger nextId = new AtomicInteger(2);

    public BookCatalog() {
        store.put("b1",
                new StoredBook("b1", "Spring Boot", "a1"));
    }

    public BookView book(String id) {
        StoredBook value = store.get(id);
        return value == null ? null : toView(value);
    }

    public List<BookView> books() {
        return store.values().stream()
                .sorted(Comparator.comparing(StoredBook::id))
                .map(BookCatalog::toView)
                .toList();
    }

    public AuthorView author(String authorId) {
        return authors.get(authorId);
    }

    public Map<String, AuthorView> authorsByIds(Set<String> ids) {
        return ids.stream()
                .filter(authors::containsKey)
                .collect(Collectors.toMap(id -> id, authors::get));
    }

    public BookView addBook(NewBookInput input) {
        if (input == null || input.title() == null
                || input.title().isBlank()) {
            throw new IllegalArgumentException(
                    "Title must not be blank");
        }

        if (!authors.containsKey(input.authorId())) {
            throw new IllegalArgumentException(
                    "Author does not exist");
        }

        String id = "b" + nextId.getAndIncrement();
        StoredBook created =
                new StoredBook(id, input.title().trim(), input.authorId());
        store.put(id, created);
        return toView(created);
    }

    private static BookView toView(StoredBook value) {
        return new BookView(
                value.id(), value.title(), value.authorId());
    }
}
```

Here the data source is a `ConcurrentHashMap` for the demo. In a real application:

- `BookCatalog` calls repositories, domain policies, transaction boundaries, or external services.
- `@Transactional` belongs on an appropriate **business operation** boundary, rather than wrapping the entire HTTP/GraphQL session indiscriminately.
- `author()` here is an in-memory lookup; against a database, plan for N+1, batch fetching, and tenant authorization.
- `IllegalArgumentException` is thrown for invalid input; without a custom `DataFetcherExceptionResolver`, GraphQL errors usually redact internal details instead of returning the raw exception message. Production should define controlled error mapping.
- `nextId` increments within one instance only and **does not survive restarts**. This is an in-memory exercise, not a persistence system or cluster-wide ID generator.

The service is unaware of `/graphql`. If you later switch transport from MVC to WebFlux, the schema and business operations **in principle do not change because of the URL**, though any blocking I/O in implementations must be revisited.

## 14. Resolver: `BookGraphQlController.java`

```java
package com.example.bookgraphql;

import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
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
    public BookView book(@Argument String id) {
        return catalog.book(id);
    }

    @QueryMapping
    public List<BookView> books() {
        return catalog.books();
    }

    @MutationMapping
    public BookView addBook(@Argument NewBookInput input) {
        return catalog.addBook(input);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public AuthorView author(BookView book) {
        return catalog.author(book.getAuthorId());
    }
}
```

**Reading each method against the schema:**

- `@QueryMapping book` maps to `Query.book(id: ID!)`.
- `@QueryMapping books` maps to `Query.books`.
- `@MutationMapping addBook` maps to `Mutation.addBook(input: NewBookInput!)`.
- `@SchemaMapping(typeName="Book", field="author")` maps to `Book.author`. The `BookView` parameter is the **source/parent object** already resolved by the GraphQL engine for `Book`; it does not come from the HTTP JSON request body.
- `@Argument` extracts the GraphQL argument bound by the engine/binder. It is **not** MVC `@RequestParam` or `@RequestBody`.

When the client asks only for `{ books { title } }`, the `Book.author` resolver is never invoked. When nested `author { name }` is requested, the GraphQL engine passes `BookView` as the source and calls `author(...)`.

**Architectural point:** The GraphQL controller does not depend on `HttpServletRequest` just to read a Book ID. It depends on GraphQL arguments and services. When authentication context is needed, use the principal/security context or `GraphQLContext` per contract — do not pull raw HTTP headers into every resolver.

## 15. Configuring and Running the HTTP Transport

**`src/main/resources/application.properties`:**

```properties
server.address=127.0.0.1
server.port=8080

spring.graphql.path=/graphql

# For local development only; do not expose dev tools by default.
spring.graphql.graphiql.enabled=false
spring.graphql.schema.printer.enabled=false
```

Run:

```bash
./gradlew bootRun
```

The sample binds loopback to reduce risk during experimentation; the GraphQL endpoint **has no Spring Security yet**, so never switch `server.address` to public or expose it to the Internet without adding authN/authZ, complexity limits, and rate limiting.

With a valid schema, the app automatically exposes **GraphQL HTTP POST** at `http://127.0.0.1:8080/graphql`. No `@PostMapping` is needed in `BookGraphQlController`.

Send a request with curl:

```bash
curl -i \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"query":"{ book(id: \"b1\") { id title author { id name } } }"}' \
  http://127.0.0.1:8080/graphql
```

Logical body right after startup:

```json
{
  "data": {
    "book": {
      "id": "b1",
      "title": "Spring Boot",
      "author": {
        "id": "a1",
        "name": "Lan"
      }
    }
  }
}
```

JSON field ordering, whitespace, and HTTP response headers are not byte-exact stdout contracts. The expected result is the **`data` matching the selection set**, without `authorId` since neither the schema nor the operation requests it.

## 16. Variables, operationName, and Mutations Sharing the Same Endpoint

A GraphQL operation can use variables instead of interpolating user input into the query string:

```graphql
query FindBook($id: ID!) {
  book(id: $id) {
    id
    title
  }
}
```

HTTP body:

```json
{
  "operationName": "FindBook",
  "query": "query FindBook($id: ID!) { book(id:$id) { id title } }",
  "variables": {
    "id": "b1"
  }
}
```

Send directly:

```bash
curl -sS \
  -H 'Content-Type: application/json' \
  --data '{"operationName":"FindBook","query":"query FindBook($id:ID!){book(id:$id){id title}}","variables":{"id":"b1"}}' \
  http://127.0.0.1:8080/graphql
```

`operationName` is required when a document defines multiple operations and one must be chosen; if a document has a single operation, it can be optional depending on protocol/client.

Mutation:

```bash
curl -sS \
  -H 'Content-Type: application/json' \
  --data '{"query":"mutation Add($input:NewBookInput!){addBook(input:$input){id title author{name}}}","operationName":"Add","variables":{"input":{"title":"GraphQL Design","authorId":"a2"}}}' \
  http://127.0.0.1:8080/graphql
```

On a freshly started server with no prior mutations, the result is:

```json
{
  "data": {
    "addBook": {
      "id": "b2",
      "title": "GraphQL Design",
      "author": {
        "name": "Minh"
      }
    }
  }
}
```

This ID **depends on in-memory state**; if other books were added earlier, the ID increments. Do not treat demo output as a concurrency/persistence guarantee.

GraphQL `Mutation` is a mutation operation type with special root semantics per spec; the application **does not automatically gain a database transaction** simply from `@MutationMapping`. Transactionality and retry idempotency remain the service layer's responsibility.

## 17. HTTP Request Format vs. GraphQL Operation

A common modeling mistake is putting all GraphQL handling inside an HTTP adapter:

```java
// Illustrative anti-pattern, UNNECESSARY when using Spring for GraphQL:
@PostMapping("/graphql")
public Map<String, Object> graphql(@RequestBody Map<String, Object> body) {
    String query = (String) body.get("query");
    // Manually parse, look up fields, query DB, and assemble JSON...
    return Map.of();
}
```

This is only a conceptual example, not runnable code. Doing that bypasses parsing, validation, coercion, execution strategies, fragments, variables, error paths, and field semantics already built into GraphQL Java.

Cleaner separation:

```text
HTTP adapter:
  POST route, request body, headers, TLS, CORS, auth
    |
GraphQL transport:
  WebGraphQlRequest / WebGraphQlHandler
    |
GraphQL execution:
  document, operation, variables, schema validation, field selection
    |
Resolver:
  Query.book, Book.author, Mutation.addBook
    |
Service:
  canRead, findBook, addBook, transaction
```

With `@QueryMapping`, the resolver knows `id` and source/arguments, and **need not** know the HTTP method. Mapping the HTTP request to GraphQL execution is infrastructure's job.

If you want a REST endpoint running alongside GraphQL, write a separate `@RestController` calling the **same service**. Neither force a REST controller to act as a GraphQL parser nor force the GraphQL schema to mirror every REST DTO.

## 18. Do Not Confuse GraphQL Schema with Java Reflection or JPA Schema

Three concepts share the word "schema" yet are fundamentally different:

| Component | Description | Example |
| --- | --- | --- |
| GraphQL schema | Public API contract: types, nullability, queries, mutations | `type Book { id: ID!, author: Author! }` |
| Java type model | Implementation classes/records/POJOs | `BookView`, `StoredBook`, `AuthorView` |
| Database schema | Tables, columns, keys, indexes, constraints | `book(id, title, author_id)` |

There is no rule that a GraphQL field `author` must be a Java property `BookView.getAuthor()` or a SQL column `author`. It can be resolved by `@SchemaMapping` calling another catalog system.

By default, Java reflection **does not generate a GraphQL schema from arbitrary classes** in the schema-first Spring for GraphQL model shown here. Code-first/auto-generation tools exist, yet they represent a different architectural decision. In this lesson, **SDL is the source of the contract**.

If you rename database column `author_id` to `writer_ref` while keeping `Book.author` in the API, only the repository/mapper changes. If you rename GraphQL field `author` to `writer`, that is a breaking contract change affecting clients even though the database did not change.

## 19. Nullability and Propagation: A Field Error Can Affect Parent Data

GraphQL nullability uses `!`:

```graphql
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Book {
  id: ID!
  title: String!
  author: Author!
}
```

Cases:

- `Query.book` can be `null` when a book does not exist.
- `Book.author` is non-null. If the resolver cannot find the author and returns `null`, GraphQL Java records an execution error and **bubbles `null` up** to the nearest nullable ancestor.
- `[Book!]!` guarantees a non-null list with non-null elements; an error turning one element null can bubble and make **the entire list field** null, or higher depending on parent schema nullability.

An illustrative GraphQL response when a non-null field fails **might** contain:

```json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "A non-null field failed to resolve",
      "path": ["book", "author"]
    }
  ]
}
```

This **illustrates response shape**, not byte-exact error messages: engines, versions, and error resolvers can produce different messages/locations. Rely on `errors[].path` and schema nullability to trace root causes.

If a valid business case allows "the author may have been deleted," the contract `author: Author!` is wrong. Fix it by enforcing referential integrity or changing the schema to nullable `author: Author` (with proper migration), **never** by returning a fabricated dummy object just to satisfy non-null.

## 20. HTTP Status and GraphQL `errors`: Two Different Failure Categories

Over HTTP transport, failures can occur **before** the GraphQL engine executes:

- Unable to route `/graphql`.
- Request body is not valid/readable JSON.
- `Content-Type` or HTTP method is rejected by the endpoint.
- Proxy/WAF blocks the call, or auth returns 401/403 ahead of GraphQL.
- Request is too large (413) or gateway times out (504).

Failures can also occur **inside** GraphQL:

- Syntax error parsing the GraphQL document.
- Validation: field absent from schema or wrong argument type.
- Variable coercion error.
- Resolver throws an exception while fetching `Book`/`Author`.
- Nullability violation on a non-null field.

A GraphQL response can return `data`, `errors`, and `extensions`. Notably, **HTTP 200 can still arrive alongside `errors`**, even when sibling fields succeed. Conversely, **never claim every GraphQL error always returns HTTP 200**: status codes depend on error type, GraphQL-over-HTTP media type (`application/graphql-response+json` vs. `application/json`), and transport implementation/version. A client writing `if (response.status == 200)` and treating it as unconditional success is wrong.

Illustrative partial-success response:

```json
{
  "data": {
    "book": {
      "id": "b1",
      "title": "Spring Boot",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Not authorized to load author",
      "path": ["book", "author"]
    }
  ]
}
```

This response is valid only if the contract **allows** `Book.author` to be nullable. If the schema says `Author!`, `data` must follow null propagation. When writing tests, check both schema nullability and GraphQL `errors` rather than inventing examples that violate the contract.

**Two failure dimensions to monitor:** HTTP method/status/headers for transport, and GraphQL `errors[].message`, `path`, `locations`, `extensions` for execution. Never rely solely on HTTP status codes to map GraphQL errors.

## 21. `DataFetcherExceptionResolver`: Translating Business Errors to GraphQL Errors

During GraphQL execution, exceptions from `@SchemaMapping`/data fetchers are handled by GraphQL Java exception resolution. Spring for GraphQL provides `DataFetcherExceptionResolver` and `@GraphQlExceptionHandler`.

**Optional integration example**, not required to run the demo above:

```java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.execution.DataFetcherExceptionResolverAdapter;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Component;

@Component
public class BookErrorResolver extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable error, DataFetchingEnvironment environment) {
        if (error instanceof IllegalArgumentException) {
            return GraphqlErrorBuilder.newError(environment)
                    .errorType(ErrorType.BAD_REQUEST)
                    .message("Invalid book input")
                    .build();
        }
        return null;
    }
}
```

This is an **example integration class** requiring the proper package and Spring GraphQL dependency, and it should map only well-defined business exceptions rather than flattening every `IllegalArgumentException` app-wide into one generic error. Returning `null` lets other resolvers/the framework handle it. Verify the `ErrorType` enum and API against your running version.

GraphQL parse/validation errors occur **before** data fetchers run, so a field `DataFetcherExceptionResolver` will not handle request-level syntax errors. Subscription stream errors after the `Publisher` starts also follow subscription exception resolution rules.

Never place stack traces, SQL, tokens, file paths, or sensitive details in GraphQL `errors.message` for public clients. Use correlation/execution IDs in internal logs and controlled response extensions where appropriate.

## 22. Field Resolvers Can Trigger N+1: `@BatchMapping` and DataLoader

Suppose a query fetches 100 books:

```graphql
{
  books {
    id
    title
    author {
      name
    }
  }
}
```

If `Query.books` queries the database once and `Book.author` queries the database **once per book**, the total can be **1 + 100 queries**. Over HTTP there is still **a single POST `/graphql`**, so counting HTTP requests hides the repository-layer N+1 problem.

GraphQL Java supports `DataLoader` and Spring for GraphQL provides `@BatchMapping` to group parent keys into a batch. With many books, provide a service API like `authorsByIds(Set<String>)` backed by a single bulk repository call rather than looping `findById` per key.

The demo already has `BookCatalog.authorsByIds(...)`. You can **replace** `@SchemaMapping(typeName="Book",field="author")` in `BookGraphQlController` with:

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<BookView, AuthorView> author(List<BookView> books) {
    Set<String> ids = books.stream()
            .map(BookView::getAuthorId)
            .collect(Collectors.toSet());

    Map<String, AuthorView> batch = catalog.authorsByIds(ids);
    Map<BookView, AuthorView> result = new LinkedHashMap<>();

    for (BookView book : books) {
        result.put(book, batch.get(book.getAuthorId()));
    }
    return result;
}
```

This is an **integration replacement snippet**: in addition to existing imports, import `@BatchMapping`, `Map`, `Set`, `Collectors`, and `LinkedHashMap`. **Do not keep both `@SchemaMapping` and `@BatchMapping` for the same field** expecting them to cooperate: both attempt to register a resolver for `Book.author`.

`BookView` in the demo implements `equals`/`hashCode` by ID so it works cleanly as a map key. For multi-tenant data, use a sufficiently strong identity (combining tenant + ID) to avoid key collisions. `@BatchMapping` supports returning `Map<Parent, Child>` or other documented types. In production, `authorsByIds` must genuinely batch at the repository, such as `SELECT ... WHERE id IN (...)`; running `findById` in a loop inside the service means **a batch-shaped API alone does not eliminate N+1**.

DataLoader normally caches per **single GraphQL request**, not across the whole application. Caching results across different users/tenants without proper authz scoping in the key can leak data.

## 23. Why the Schema Does Not Guarantee Data Security

A schema might expose:

```graphql
type Query {
  invoice(id: ID!): Invoice
}

type Invoice {
  id: ID!
  total: Float!
  ownerEmail: String!
}
```

If the resolver merely calls `repository.findById(id)` without verifying the caller owns or has permission for that invoice, any client allowed to send GraphQL requests can enumerate IDs and read other users' records. GraphQL validation checks only **whether fields exist** and **whether types match**; it has no concept of business owners, tenants, or roles.

Check security at multiple layers:

- **Transport level:** request authentication, TLS, CORS, CSRF policy for cookie sessions, HTTP body limits.
- **Operation/field level:** resolver/method security, roles/permissions for mutations and sensitive fields.
- **Object/data level:** ACLs, tenant scoping, and owner checks in services/repositories. In particular, `Query.book` must query within the verified tenant.
- **Nested field level:** `Book.author` and `Invoice.ownerEmail` must also check permissions when needed rather than assuming parent access grants child access.
- **Bulk loader level:** batch loads must not mix data across users/tenants; DataLoader caching must stay properly scoped.

Illustrative book-read policy:

```java
// Business policy illustration, not standalone:
BookRecord record = repository.findByIdAndTenant(id, currentTenant)
        .orElseThrow(NotFoundException::new);

authorization.checkCanRead(principal, record);
return mapper.toBookView(record);
```

Types `BookRecord`, `NotFoundException`, `repository`, `authorization`, and `mapper` represent real-system components not present in the in-memory demo. Enforcing access checks in the **service layer** ensures REST endpoints, scheduled jobs, and GraphQL resolvers all obey the same policy.

Never rely solely on `@PreAuthorize("isAuthenticated()")` on `/graphql` assuming all objects and fields are protected. One HTTP endpoint can query many resource types with very different access rules.

## 24. Passing HTTP Metadata into GraphQL Context Safely

Certain transport metadata (trace ID, correlation ID, authenticated principal, verified tenant) must be available during field resolution. Spring for GraphQL provides **`WebGraphQlInterceptor`**, sitting right at the transport/execution boundary:

```text
HTTP headers / security principal
        |
        v
WebGraphQlInterceptor
  validate/normalize selected metadata
  add to GraphQLContext
        |
        v
ExecutionGraphQlService
        |
        v
@QueryMapping / @SchemaMapping / DataFetcher
  inject @ContextValue or principal
```

**Integration example**, not standalone source:

```java
@Bean
WebGraphQlInterceptor correlationInterceptor() {
    return (request, chain) -> {
        String value = request.getHeaders().getFirst("X-Correlation-Id");
        String correlationId = normalizeOrGenerate(value);

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(contextBuilder ->
                        contextBuilder.put("correlationId", correlationId))
                        .build());

        return chain.next(request);
    };
}
```

Here `normalizeOrGenerate(...)` is an application helper requiring matching imports/config. **Never trust** client-supplied `X-User-Id` or `X-Tenant-Id` headers from public callers. Place authentication/tenant details into `GraphQLContext` only after verification by the security layer or a trusted gateway.

In a resolver:

```java
@QueryMapping
public String trace(@ContextValue String correlationId) {
    return correlationId;
}
```

This snippet requires `Query.trace` in the schema, annotation imports, and context populated by the interceptor. `GraphQLContext` is **request-scoped execution metadata**, not a JPA persistence context or Servlet session. Never turn it into shared singleton global state.

In Spring MVC, asynchronous fetchers may execute on different threads, so do not assume custom `ThreadLocal` or `RequestContextHolder` state propagates automatically without registering proper context propagation. In WebFlux, Reactor context and reactive execution require framework-supported propagation. A **standardized context** is far cleaner than reading raw HTTP headers in every resolver.

## 25. Schema Evolution and Contract Compatibility

Because GraphQL APIs are defined by a schema, clients couple to **field names, types, nullability, and arguments**. Some changes are usually safe, while others break clients:

| Schema Change | Compatibility Impact to Consider |
| --- | --- |
| Adding a new field to an object type | Usually backward-compatible with existing clients |
| Adding an optional argument with a default/safe behavior | Usually compatible |
| Removing or renaming an active field | Breaking change |
| Nullable `Book` → non-null `Book!` | Can affect runtime nullability/compatibility |
| Non-null `Book!` → nullable `Book` | Can break clients expecting non-null |
| Adding a required argument without a default | Breaking change for existing queries |
| Changing `ID!` to an incompatible type | Breaking change |
| Changing resolver permissions/content | Can alter behavior even when SDL is unchanged |
| Changing DB entity/column while keeping contract | Usually transparent to clients if mapped properly |

GraphQL supports `@deprecated(reason: "...")` in the schema to mark old fields/enum values; this is a migration signal, not something that stops old clients from querying the field. Typically you need schema diffs, deprecation policies, usage telemetry, and contract tests before removing fields.

**Do not treat renaming a Java class as changing a public GraphQL field** when `@SchemaMapping(typeName=...,field=...)` and the schema stay unchanged. Conversely, editing the SDL can break queries even when Java controller names and `/graphql` remain untouched.

GraphQL schema registries, federation, or gateways add composition responsibilities across services, yet the fundamental boundary remains: public schema → runtime wiring/resolvers → domain/backends.

## 26. Do Not Confuse Schema Validation with Business Input Validation

The GraphQL engine can reject an operation before any resolver runs:

```graphql
{
  book(id: 123) {
    nonexistent
  }
}
```

`nonexistent` is not in `type Book` → **schema validation error**; no `@QueryMapping`/`@SchemaMapping` runs for that field. Scalar coercion rules (e.g., `ID` accepting both string and integer literals per spec) are separate and never make an undefined field valid.

Yet a schema-valid GraphQL operation can still be invalid in business terms:

```graphql
mutation {
  addBook(input: {title:"", authorId:"a99"}) {
    id
  }
}
```

The SDL accepts `title` as `String!` because an empty string **is not null**, and `authorId` has type `ID`. The service must validate non-blank titles, author existence, permissions, quotas, and domain invariants.

Validation layers typically include:

1. **HTTP codec:** can the body parse as JSON?
2. **GraphQL parser/validator:** is the document syntactically valid and compliant with the schema?
3. **Argument binding:** does the input object bind cleanly to the Java type?
4. **Bean Validation/Business validation:** field constraints, existence, permissions, uniqueness, state transitions?
5. **Persistence constraints:** foreign keys, unique indexes, transactional consistency.

Do not flatten everything into one HTTP `try/catch` returning generic `400`. GraphQL clients distinguish **global request errors** from **field errors with `path`**.

## 27. HTTP Caching, Methods, and Shared-Endpoint Limits

In REST, caching often relies on URL, HTTP method, status, `ETag`, and cache headers. In GraphQL, many operations share **POST `/graphql`**, so **URL-based caching alone cannot** distinguish data by query, variables, user, or authorization context.

Consider:

- Never cache private responses merely because the URL is `/graphql` and HTTP status is 200.
- If using persisted queries or CDN caching, cache keys must incorporate operation/query identity, variables, and appropriate auth/tenant scopes.
- Avoid putting tokens or sensitive data in query-string URLs when GraphQL-over-GET is enabled on supporting infrastructure.
- Request body size limits do not protect against huge **GraphQL query depth/cost**; a tiny query in bytes can fan out into thousands of database calls.
- Enforce pagination, bounded list sizes, depth/cost limits, rate limits, time budgets, and DataLoader/batching.
- Side-effecting mutations require authorization, idempotency/retry strategies, and auditing.

Spring Boot 3.3 exposes **POST `/graphql`** by default. Do not assume all GraphQL-over-HTTP implementations support GET, multipart uploads, or streaming identically; apply protocol/client policies matching your exact version and use case.

GraphQL selection sets prevent **payload over-fetching**, yet do not guarantee fewer backend queries or lower CPU if resolvers eagerly load everything anyway. Real performance depends on resolver, service, and repository design.

## 28. Spring MVC and WebFlux: Different Transports, Shared GraphQL Contract

GraphQL Java execution is transport-agnostic. Spring for GraphQL supports both Spring MVC/Servlet and Spring WebFlux:

| Aspect | MVC | WebFlux |
| --- | --- | --- |
| HTTP runtime | Servlet API, commonly embedded Tomcat | Reactive server, commonly Reactor Netty |
| Boot GraphQL endpoint | `/graphql` via Boot property | `/graphql` via same property |
| GraphQL engine | `GraphQlSource` / GraphQL Java | `GraphQlSource` / GraphQL Java |
| Schema SDL | Identical contract | Identical |
| Resolver annotations | `@QueryMapping`, `@SchemaMapping`, ... | Same annotations |
| Data fetchers | Blocking or async depending on method/service | Reactive `Mono`/`Flux` and async |
| Context propagation | Servlet/`ThreadLocal` needs async care | Reactor context needs reactive care |
| Streaming/subscription | SSE/WebSocket per web transport | SSE/WebSocket per reactive transport |
| Blocking I/O | Uses appropriate worker threads | Never block the Netty event loop |
| Error contract | GraphQL `data`/`errors` | GraphQL `data`/`errors` |

You can migrate an app from MVC to WebFlux without changing the SDL, yet **that does not turn blocking JPA repository calls into non-blocking calls**. Running blocking JPA directly on Reactor Netty's event loop can stall the server. Choose an appropriate execution strategy/scheduler or reactive data access.

A `Mono` returned from a reactive resolver is adapted by Spring GraphQL into an async result for GraphQL Java execution. A `Flux` outside a subscription has different semantics from a `Flux` in a GraphQL subscription; do not assume returning `Flux<Book>` from any query automatically creates an SSE stream to the browser.

**Choose transport and data access according to workload**, rather than switching stacks blindly because someone claimed "GraphQL is faster on WebFlux."

## 29. GraphQL Subscriptions and WebSocket: Operation vs. HTTP Connection

A GraphQL schema can declare:

```graphql
type Subscription {
  newBooks: Book!
}
```

`Subscription` defines a GraphQL **stream operation**. Declaring it in the schema does not enable a WebSocket endpoint by itself. To emit events you need:

1. GraphQL schema field `Subscription.newBooks`.
2. An event-source resolver, typically `@SubscriptionMapping` returning `Flux<BookView>` or `Publisher`.
3. A configured **streaming transport** (GraphQL WebSocket, or SSE where supported).
4. Per-subscriber cancellation/cleanup when clients disconnect.
5. AuthN/AuthZ, timeouts, rate limits, and backpressure/replay policies if required.

Spring Boot 3.3 disables the GraphQL WebSocket endpoint by default; set `spring.graphql.websocket.path` and add the dependencies required by MVC or WebFlux. WebSocket uses its own handshake and GraphQL transport protocol; **it is not** just a long-lived HTTP POST.

When a GraphQL subscription runs over SSE, the HTTP transport uses `text/event-stream` with its own disconnect semantics. Even then, the schema and resolvers stay in the GraphQL layer. **Do not embed connection/reconnect logic inside a domain `Book` entity.**

With real streaming, errors after response headers have been sent cannot arbitrarily change the HTTP status code into JSON. Rely on the error/cancellation mechanics of the chosen GraphQL subscription transport.

## 30. GraphQL Operations and Spring Security: Protecting the Right Layer

Blocking unauthenticated callers at `POST /graphql` is **only step one**, insufficient for field-level permissions. Behind a single GraphQL endpoint, permissions vary by operation:

```text
Query.books                 -> public or user-level
Query.book                  -> per tenant/owner
Book.author                 -> field-level policy
Mutation.addBook            -> requires books:write
Mutation.deleteBook         -> may require admin/owner
Subscription.newBooks       -> scoped by tenant/topic
```

Available mechanisms:

- Web security filter chain: request authentication, cookie/bearer handling, CSRF where applicable, CORS, and transport access.
- Service authorization: tenant/owner checks and business invariants.
- Method security such as `@PreAuthorize`, when enabled and applied across real proxy/bean boundaries.
- Data fetcher–level checks for sensitive fields.
- Batch loaders scoped per caller and request.

Illustrative method security snippet **which must live in an app with Spring Security configured**, absent from the non-security demo:

```java
@PreAuthorize("hasAuthority('SCOPE_books:write')")
@MutationMapping
public BookView addBook(@Argument NewBookInput input) {
    return catalog.addBook(input);
}
```

Never assume adding that annotation alone protects the endpoint without `@EnableMethodSecurity`, principal authentication, and real JWT scopes/authorities configured. Furthermore, `@PreAuthorize` on `Mutation.addBook` does not replace checking authorization on `authorId`, `tenantId`, and domain policies.

**Never accept an unverified `X-Tenant-Id` header directly from a browser** to pick a tenant and let resolvers query rows by it; tenant identity must come from the verified auth/trust boundary.

## 31. `GraphQlTester`: Testing Schema + Resolvers Without HTTP

Spring Boot provides **`@GraphQlTest`**, a test slice loading only GraphQL-related components without starting a real HTTP server. This separation is valuable: it lets you test **contracts/schemas/resolvers** independently of URLs, Servlet filters, and TLS.

**`src/test/java/com/example/bookgraphql/GraphQlSchemaTest.java`:**

```java
package com.example.bookgraphql;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest(BookGraphQlController.class)
@Import(BookCatalog.class)
class GraphQlSchemaTest {

    @Autowired
    private GraphQlTester tester;

    @Test
    void nestedAuthorIsResolvedBySchemaMapping() {
        tester.document(
                "{ book(id: \"b1\") { title author { name } } }")
                .execute()
                .path("book.title")
                .entity(String.class)
                .isEqualTo("Spring Boot");

        tester.document(
                "{ book(id: \"b1\") { author { name } } }")
                .execute()
                .path("book.author.name")
                .entity(String.class)
                .isEqualTo("Lan");
    }

    @Test
    void missingBookIsNullableByContract() {
        tester.document("{ book(id: \"missing\") { id } }")
                .execute()
                .path("book")
                .valueIsNull();
    }
}
```

`@GraphQlTest` auto-configures GraphQL infrastructure and does not scan arbitrary `@Service` beans. Because the demo controller depends on `BookCatalog`, the test uses `@Import(BookCatalog.class)` to register the in-memory service. When real services talk to a database, use mocks/fakes rather than pulling the full database into the test slice.

`GraphQlTester` asserts responses using **GraphQL paths relative to `data`**, such as `book.author.name`. Unexpected GraphQL errors normally fail the test, catching mapping/schema issues. This test does not prove CORS, proxy headers, or the live `/graphql` HTTP route work — that belongs to the transport layer.

## 32. Testing Real HTTP: `HttpGraphQlTester` Verifies Transport and Execution

Spring Boot 3.3 supports `HttpGraphQlTester` when `spring-graphql-test` and test WebFlux/WebTestClient dependencies are present per docs. With `@SpringBootTest(webEnvironment=RANDOM_PORT)`, a real HTTP server runs and the tester calls the endpoint through the web transport.

**`src/test/java/com/example/bookgraphql/GraphQlHttpTest.java`:**

```java
package com.example.bookgraphql;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GraphQlHttpTest {

    @Autowired
    private HttpGraphQlTester tester;

    @Test
    void queryWorksOverHttpTransport() {
        tester.document(
                "query($id: ID!) { book(id:$id) { id title } }")
                .variable("id", "b1")
                .execute()
                .path("book.id")
                .entity(String.class)
                .isEqualTo("b1");
    }

    @Test
    void mutationBindsGraphQlInputObject() {
        tester.document(
                "mutation { addBook(input: " +
                "{title:\"API Design\", authorId:\"a1\"}) " +
                "{ title author { name } } }")
                .execute()
                .path("addBook.author.name")
                .entity(String.class)
                .isEqualTo("Lan");
    }
}
```

Run:

```bash
./gradlew test
```

**Expected outcome** when test dependencies, schema, Java code, and runtime match: all tests **PASS**. Gradle stdout formatting varies across versions and runtimes.

Using the two tests to isolate boundaries:

- `GraphQlSchemaTest` PASSES while `GraphQlHttpTest` FAILS → inspect HTTP transport path, security/filters/codecs/server config.
- Both FAIL reporting `Query.book` missing from schema → inspect SDL, resolver mappings, and `GraphQlSource`.
- Both PASS yet querying many books is slow → inspect application service, data loaders, repositories, and query cost.
- Query PASSES for one user yet leaks another tenant's data → **authorization** bug, not schema syntax.

Do not rely solely on a `@WebMvcTest` REST test to conclude GraphQL field resolution works; `@GraphQlTest` is the appropriate slice for schema/resolvers.

## 33. Verifying Real Errors: Query Validation vs. Business Data

Send a query with a non-existent field:

```bash
curl -i \
  -H 'Content-Type: application/json' \
  --data '{"query":"{ book(id: \"b1\") { hiddenPassword } }"}' \
  http://127.0.0.1:8080/graphql
```

Since the SDL does not define `Book.hiddenPassword`, GraphQL validation rejects the field. The response contains validation `errors`; **exact HTTP status varies by GraphQL-over-HTTP media type and implementation**, so do not hardcode a fixed 200 output.

Query a non-existent book:

```bash
curl -sS \
  -H 'Content-Type: application/json' \
  --data '{"query":"{ book(id: \"unknown\") { id title } }"}' \
  http://127.0.0.1:8080/graphql
```

Because `BookCatalog.book` returns `null` and schema `Query.book: Book` is nullable, the logical response is:

```json
{"data":{"book":null}}
```

If a mutation passes `title:""` (empty string), schema input `String!` allows it structurally, yet the service throws `IllegalArgumentException`. Under default exception handling, the response includes a GraphQL error per Spring GraphQL's mechanism; the message may be redacted rather than literally `"Title must not be blank"`.

**Distinction:** unknown field is a **schema validation error before resolvers**; unknown book is a schema-allowed **null business result**; blank title is a **business validation failure inside the resolver/service**. Never flatten all three into one generic HTTP 500 that hides semantics.

## 34. `GraphQlSource`, Manual Wiring, and Custom Scalars

Annotated controllers are standard in Spring for GraphQL, yet at runtime GraphQL Java executes **data fetchers** attached to the schema via runtime wiring. When you need manual field fetchers, custom scalars, or type resolvers, use `RuntimeWiringConfigurer`/`GraphQlSourceBuilderCustomizer`.

Conceptual example:

```java
@Bean
RuntimeWiringConfigurer wiringConfigurer() {
    return wiring -> wiring.type(
            "Query",
            builder -> builder.dataFetcher(
                    "serverTime",
                    environment -> "2026-01-01T00:00:00Z"));
}
```

This is an **integration snippet**, requiring `Query.serverTime: String!` in the schema, imports for `RuntimeWiringConfigurer` and `Bean`, and no duplicate `@QueryMapping serverTime` binding. The literal timestamp illustrates output rather than a live system clock.

Key components:

- `GraphQlSource` builds the engine from SDL plus wiring.
- `RuntimeWiringConfigurer` registers custom `DataFetcher`s and scalars.
- `AnnotatedControllerConfigurer` registers resolver methods into runtime wiring.
- `ExecutionGraphQlService` accepts a GraphQL request object and invokes GraphQL Java.
- Web transports handle HTTP/WebSocket/RSocket details and delegate to the execution service.

**Every schema field must have a valid fetch path**: an annotated resolver, custom `DataFetcher`, or default property fetcher. Successful schema validation does not prove every business field resolves properly; tests must cover key fields.

If the schema defines a custom scalar `DateTime`, configure explicit coercion/serialization and test values. Never assume Java `LocalDateTime` serializes cleanly in GraphQL Java just because the class exists; the SDL scalar and Java runtime coercing must be wired together.

## 35. Observing Errors by Layer in Production

| Symptom | Suspected Layer | What to Check |
| --- | --- | --- |
| POST `/graphql` 404 | HTTP route/transport | `spring.graphql.path`, web starter dependencies, base/context path |
| Startup reports missing schema | SDL resources | `.graphqls`/`.gqls`, `src/main/resources/graphql`, classpath |
| Startup reports field/type mismatch | SDL/wiring | Schema definitions, duplicate types, mappings |
| Query field does not exist | GraphQL validation | SDL type, selected field, client version |
| `@QueryMapping` method not called | GraphQL execution/wiring | `@Controller` scan, method/schema field names, request validation |
| Scalar field unexpectedly null | Java property fetch/model | JavaBean getter, mapping, nullability |
| Query has both `data` and `errors` | GraphQL field execution | `errors.path`, exception resolver, null propagation |
| HTTP 200 yet client treats as failure | Client GraphQL error handling | Read both `errors` and `data`, not status alone |
| Books query slow with many authors | Resolver/data access | N+1, `@BatchMapping`, DB query count |
| GraphQL returns another tenant's data | Authorization/service | Owner/tenant checks, DataLoader cache scope |
| Proxy blocks CORS preflight | HTTP/gateway | Origin policy, `OPTIONS` handling, Spring Security |
| WebSocket subscription fails to connect | Streaming transport | WebSocket starter/path, handshake/auth/idle timeout |
| Mutation partially modifies DB | Business transaction | Service transaction boundaries/rollback |
| Schema test PASSES, HTTP test FAILS | Transport | HTTP routing, filters, server port, JSON |
| HTTP endpoint works yet GraphiQL 404s | Dev tooling | `spring.graphql.graphiql.enabled` defaults to false |
| Schema printer returns nothing | Dev tooling | `spring.graphql.schema.printer.enabled` defaults to false |

Diagnose in order: **public request URL → HTTP filter/route → `WebGraphQlHandler`/interceptor → parse/validate/schema → field resolver → service/repository → GraphQL result → HTTP serialization**. Identify the **first failing layer** before editing code; never fix a `@SchemaMapping` bug by adding a REST `@PostMapping`.

Metrics/tracing should separate HTTP route status/latency, GraphQL operation/field timings, data fetcher errors, batch sizes, downstream DB/API latencies, and query complexity. Avoid using raw GraphQL queries or user IDs as unbounded-cardinality metric tags, and never log variables containing PII.

## 36. Checklist for Designing a Healthy GraphQL API

Before release:

1. Maintain a clear, version-controlled SDL schema with contract tests.
2. Configure the right transport starter: MVC/WebFlux; HTTP `/graphql` per Boot 3.3.
3. Do not create a `@PostMapping("/graphql")` colliding with the framework endpoint without special reason.
4. Map resolvers cleanly to GraphQL fields via `@QueryMapping`, `@MutationMapping`, `@SchemaMapping`; do not confuse with HTTP mappings.
5. Do not expose raw domain/JPA entities unintentionally; use controlled DTOs/projections.
6. Validate input DTOs in business logic rather than relying solely on GraphQL `String!`/`ID!`.
7. Enforce authorization at object/tenant/field levels, including nested resolvers and batch loaders.
8. Bound expensive or abusive workloads with query cost/depth limits, pagination, and data loaders.
9. Handle errors per GraphQL semantics; never treat HTTP 200 as unconditional success.
10. Keep stack traces, sensitive data, and SQL details out of `errors.message`.
11. Design HTTP CORS, CSRF, TLS, size limits, authentication, and proxy trust boundaries independently of the schema.
12. Write tests for **non-HTTP GraphQL execution** (`@GraphQlTest`) and **HTTP transport** (`@SpringBootTest`/`HttpGraphQlTester`).
13. Review schema compatibility for nullability, arguments, enums, renames, and deprecations.
14. If subscriptions are enabled, design transport, auth, cancellation, backpressure, and reconnect handling.
15. Instrument observability for execution/field errors, DB query counts, request correlation, and timeouts.

When a parallel REST endpoint is needed, reuse the **same business service** behind two separate adapters: a REST `@RestController` and a GraphQL `@Controller`/`@QueryMapping`. Avoid duplicating business rules across adapters, which causes diverging authorization behavior.

## 37. Self-Assessment and Exercises

1. If HTTP POST `/graphql` reaches the server successfully yet the GraphQL query references a non-existent field, which layer reports the error first? Is the resolver invoked?
2. How do `@QueryMapping` and `@GetMapping` differ in routing and abstraction?
3. When `BookView.getAuthorId()` is used inside a resolver, why can't a GraphQL client query `authorId`?
4. What does `Book.author: Author!` require from the resolver? If no author exists, how does null propagation behave?
5. Why can a single GraphQL HTTP request trigger N+1 SQL queries?
6. To migrate storage from Postgres to an external API while keeping the `Book.author` contract, which layers change and which stay intact?
7. Why does the schema not replace ACL/tenant checks for `Query.book(id: ID!)`?
8. What does `GraphQlTester` in `@GraphQlTest` test, and what does it not test?
9. Why must real HTTP tests check both `data` and `errors` rather than HTTP status alone?
10. How does `GraphQLContext` differ from `HttpServletRequest`, JPA persistence context, and singleton caches?
11. When adding a new GraphQL field, why isn't a separate Java resolver always required?
12. If a Servlet MVC backend uses blocking repositories, should you switch to WebFlux just because you added GraphQL?
13. When enabling GraphiQL and introspection, what security risks must be reviewed, and what **is not** solved by disabling introspection?
14. A query requests 10,000 nested objects while its HTTP body is only a few hundred bytes. Why is a request body limit insufficient?
15. A mutation resolver throws `IllegalArgumentException` after writing part of the database changes. Should SDL, the GraphQL exception resolver, or the business transaction handle rollback?

**Exercise A:** Run the demo from Sections 10–16. Send a query selecting only `title`, then one selecting `author { name }`; observe each response contains only the requested fields.

**Exercise B:** Temporarily remove `@SchemaMapping(typeName="Book",field="author")` and query `author`. Observe the default data fetcher result and non-null contract; then restore the resolver. Do this only in a learning environment.

**Exercise C:** Replace `@SchemaMapping Book.author` with `@BatchMapping` from Section 22, seed at least 20 books, swap the in-memory lookup for a mocked bulk repository, and count backend calls. Verify call counts do not scale linearly with book count.

**Exercise D:** Write a `GraphQlTester` test verifying `book(id:"missing")` returns null; send a `curl` HTTP request for a non-existent field and classify errors by **transport/validation/business**.

**Exercise E:** Add a REST endpoint reading `BookCatalog.book` without duplicating service logic; compare REST HTTP routing against GraphQL field routing and how authorization is checked.

## 38. Conclusion: One HTTP Endpoint, Many GraphQL Fields, One Independent Domain Layer

**Memorable boundaries:**

```text
HTTP runtime:
  how requests reach the app and responses leave the app

GraphQL schema:
  which operations, fields, and shapes clients may request

GraphQL execution + resolvers:
  where valid fields load data from and how errors are shaped

Domain/data model:
  what the real data is, who may access it, and valid state transitions
```

In Spring Boot 3.3, `spring-boot-starter-graphql` together with a web starter connects HTTP `/graphql` to the GraphQL Java engine. **The SDL in `resources/graphql` is the public contract**, while `@QueryMapping`, `@MutationMapping`, and `@SchemaMapping` are field resolvers. Services, domain logic, and repositories sit behind them and should never depend on how HTTP wraps the GraphQL query body. Keeping these boundaries clear makes the application testable, limits accidental data exposure, and lets you swap transports, persistence, or batch loading while keeping the schema stable.

### Official References

- Spring Boot 3.3, Spring for GraphQL — schema, transports, wiring, tests: https://docs.spring.io/spring-boot/3.3/reference/web/spring-graphql.html
- Spring Boot 3.3, Testing Spring Boot Applications — GraphQL tests: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3, Common Application Properties — `spring.graphql.*`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring for GraphQL — Annotated Controllers: https://docs.spring.io/spring-graphql/reference/controllers.html
- Spring for GraphQL — Request Execution and GraphQlSource: https://docs.spring.io/spring-graphql/reference/request-execution.html
- Spring for GraphQL — Testing / GraphQlTester: https://docs.spring.io/spring-graphql/reference/testing.html
- GraphQL Specification — Schema, Execution, Errors, Nullability: https://spec.graphql.org/
- GraphQL over HTTP Working Draft — request/response transport conventions: https://graphql.github.io/graphql-over-http/draft/