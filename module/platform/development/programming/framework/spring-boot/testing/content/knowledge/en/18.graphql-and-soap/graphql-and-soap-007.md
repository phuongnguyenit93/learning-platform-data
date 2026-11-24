# Testing GraphQL Resolvers Dependent on Services, DataLoaders, and Context

> **Module:** Spring Boot – testing  
> **Group:** GraphQL and SOAP  
> **Topic:** Testing resolvers dependent on services, DataLoaders, and context  
> **Primary scope:** GraphQL resolvers in Spring for GraphQL, injected services, per-request DataLoaders, `GraphQLContext`, N+1 verification, authorization boundaries, slice tests, and HTTP tests. SOAP has a distinct endpoint model and is referenced only where needed to distinguish tools.

## 1. Why must GraphQL resolvers be tested across multiple layers?

In REST, a controller typically returns a DTO whose fields are already populated. In GraphQL, clients **select fields** in a document; the runtime executes a set of data fetchers/resolvers that may span multiple services and DataLoaders:

```graphql
query {
  books {
    id
    title
    author {
      id
      displayName
    }
  }
}
```

To fulfill this document, the application can:

1. Run `@QueryMapping` for `Query.books`.
2. Call `BookService` to retrieve visible books.
3. For each book, run `@SchemaMapping(typeName="Book", field="author")`.
4. The `Book.author` resolver calls `DataLoader.load(authorId)` instead of querying the database once per book.
5. DataLoader collects keys, queries `AuthorService` in a batch, and maps results back to the right keys.
6. The request context carries **authenticated** user/tenant information or other metadata for service-level authorization.
7. The GraphQL engine constructs the `data` response and, if failures occur, returns `errors` instead of necessarily failing the whole HTTP request.

A test that merely calls `bookController.books(...)` directly does **not** verify the Schema, GraphQL Java field execution, DataLoader dispatching, response paths, or error semantics. A test that only checks that the returned JSON looks right does **not** prove batching happened instead of N+1 queries. A test that only counts service calls without checking tenant/context can miss leaking another user's data.

**The goal is to combine at least three kinds of evidence:**

- **Data:** `GraphQlTester` returns the expected fields/paths, values, nullability, and errors per schema.
- **Collaboration:** Resolvers pass the right arguments to services, and DataLoaders collect the expected keys and associate results with the right IDs.
- **Request boundaries:** Each request's tenant/principal/context reaches the loader without cache leakage across users; missing critical context fails explicitly.

## 2. Execution model and where each tool sits

```text
   GraphQL client / document
              │
              ▼
 HTTP / WebSocket / RSocket transport  ── only in transport tests
              │
              ▼
 WebGraphQlInterceptor chain           ── adds authenticated context
              │
              ▼
 ExecutionGraphQlService
              │
              ▼
 GraphQL Java execution
              │
       @QueryMapping books
              │
       BookService.visibleBooks(tenant)
              │
              ├── Book b1 ── @SchemaMapping author ──┐
              ├── Book b2 ── @SchemaMapping author ──┤ load(authorId)
              └── Book b3 ── @SchemaMapping author ──┘
                                                     │
                                      per-request DataLoaderRegistry
                                                     │
                           one or more batched dispatches of unique keys
                                                     │
                              AuthorService.findByIds(keys, tenant)
                                                     │
                                      Map<authorId, Author>
                                                     │
                                     GraphQL data / errors
```

**Distinctions:**

| Component | Responsibility | Key tests |
| --- | --- | --- |
| `@QueryMapping` | Resolves a root field on `Query` | Query document → exact list/arguments/tenant |
| `@SchemaMapping` | Resolves a nested field on a source/parent object | Exact parent field, key, and path |
| `@BatchMapping` | Auto-registers a batch resolver + DataLoader via Spring | No N+1, accurate per-parent results |
| `BatchLoaderRegistry` | Registers mapped/ordered batch loaders by name or type pair | Exact loader name, key set, context, caching |
| `DataLoader<K,V>` | Defers, batches, dispatches, and caches `load(key)` calls within one request | Single batch for co-dispatched keys, key/result mapping |
| `GraphQLContext` | Metadata attached to a GraphQL execution | Never trust unauthenticated client input; isolate requests |
| `@ContextValue` | Binds a key from `GraphQLContext` into controller methods | Presence, type, missing-context policy |
| `WebGraphQlInterceptor` | Intercepts transport requests, configures `ExecutionInput`/context | Header/auth → context, interceptor order |
| `GraphQlTester` | Tests GraphQL documents and response data/errors | Value paths, errors, variables, list/null fields |

**Note:** A GraphQL schema resolver is a `@QueryMapping`/`@SchemaMapping` method invoked through GraphQL execution. A SOAP endpoint uses a different mechanism (`@Endpoint`, `@PayloadRoot`, XML/SOAP Envelope); do not use `GraphQlTester` to test SOAP. This lesson stays squarely on topic: GraphQL resolvers and DataLoaders.

## 3. Why is fetching each author individually N+1?

Suppose `books` returns 100 books. A naive implementation:

```java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findOne(book.authorId());
}
```

This is **illustrative code**, not part of the runnable project below. If `BookService` takes one query to fetch 100 books and the resolver invokes `AuthorService` 100 times, the total can become **1 + 100** round-trips (N+1). Not every service call maps 1-to-1 to a SQL statement; this models the risk whenever the service hits a database or remote API.

Using DataLoader:

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<String, Author> loader) {
    return loader.load(book.authorId());
}
```

Spring for GraphQL integrates with GraphQL Java so `load(...)` calls within the same execution phase can be **batched**. Instead of hundreds of single calls, the loader collects unique keys and passes a `Set<String>` to a single batch function.

**Never claim "DataLoader always calls the service only once for every GraphQL query."** Batch counts also depend on GraphQL execution levels, nested fields, dispatch timing, `maxBatchSize`, query complexity, schedulers, caching settings, and request count. A test targeting a **specific query shape** can guard "for 3 books and 2 author IDs, only 1 batch"; that does not imply every document in the app executes in 1 batch.

### 3.1. Keys and values must match accurately

Example keys to load:

```text
load("a-1")  ─┐
load("a-2")   ├── batch Set{"a-1","a-2"} → Map{"a-1":AuthorA,"a-2":AuthorB}
load("a-1")  ─┘

  Two calls to load("a-1") within one request
  can share the cached future/result when caching is enabled.
```

With a mapped loader, the batch function returns `Map<K,V>` so the framework matches entries by key; **the iteration order of the Set or Map must not dictate GraphQL output order**. With an ordered loader returning `List<V>`, list order must match the input key order. Tests must catch "a-1 mistakenly returned AuthorB," not merely check element count.

### 3.2. DataLoader cache is not a global application cache

GraphQL Java DataLoaders normally cache loaded values by key **within a single request's `DataLoaderRegistry`**. Spring for GraphQL and `BatchLoaderRegistry` register fresh DataLoaders for each execution.

If you manually hold a singleton/global `DataLoader` or share a `DataLoaderRegistry` across requests, a key like `"a-1"` could return user A's data to user B when output depends on tenant or permissions. **Never share a per-request loader cache across security boundaries.** If an explicit shared cache is used, its cache key must include every authorization dimension alongside proper invalidation/TTL.

## 4. Service, DataLoader, and context are three distinct boundaries

### 4.1. Testing resolvers with mocked services

`@GraphQlTest(BookGraphQlController.class)` is Spring Boot's slice for GraphQL controllers. It configures GraphQL infrastructure and relevant beans without scanning every `@Service` and `@Repository`. To instantiate the controller, supply service collaborators with `@MockitoBean`.

What the test proves: schema mapping, GraphQL field paths, argument resolution, and that resolvers forward the right inputs to services.

What the test **does not** prove: that the real `BookService` queries the database properly, that the live HTTP endpoint enforces security filters, or that a production loader connects to external services—whenever those components are mocked.

### 4.2. Testing DataLoader with mocked services

DataLoader belongs to graph execution; the proper way to catch N+1 issues is typically:

- Keep DataLoader registration/configuration **real**.
- Mock `AuthorService` at the data boundary.
- Execute a GraphQL document requesting nested fields across multiple parents.
- Assert **exact values per parent** and `verify(authorService, times(1)).findByIds(expectedKeys, expectedTenant)` for that specific query shape.
- Repeat with two tenant requests to verify context propagation and cache isolation.

If you mock the DataLoader itself in tests, you skip real dispatch, batching, and caching, so you cannot claim N+1 is solved.

### 4.3. Testing context at two levels

- **Execution context test:** build an `ExecutionGraphQlServiceTester` and configure `ExecutionInput.graphQLContext` in the test. This verifies resolvers and loaders read the expected context **once present in execution**; it **skips** HTTP and `WebGraphQlInterceptor`.
- **Transport context test:** use `HttpGraphQlTester` over a Spring MVC/WebFlux test client or real server, passing mock headers/cookies/tokens. `WebGraphQlInterceptor` safely moves metadata into `GraphQLContext` before running resolvers and loaders. This verifies the full chain **transport → interceptor → context → service**.

Never run a direct execution test and claim an HTTP request missing a header will be rejected: that test **bypassed** transport and interceptors.

### 4.4. Context alone does not equal authorization

`GraphQLContext` can hold traceId, locale, feature flags, tenant, or principal. **A client-supplied `X-Demo-Tenant` header does not prove the caller is authorized for that tenant.** In production:

- Derive identity from Spring Security `Authentication`, validated JWT claims/sessions, or trusted service-to-service auth.
- Enforce tenant/resource authorization in the service/DB layer, not only in resolvers.
- Never let clients pick an arbitrary tenant header and filter data by it without verification.
- In async/`CompletableFuture`/reactive code, understand SecurityContext/ThreadLocal/Reactor Context propagation; never rely on plain `ThreadLocal` across threads.
- Never leak access tokens or sensitive PII in GraphQL request logs, DataLoader keys, metrics labels, or test failure output.

**The entire sample project uses `X-Demo-Tenant` solely to demonstrate context propagation**, not authentication or authorization.

## 5. Runnable Maven project with Spring GraphQL

Uses **Java 17, Maven, Spring Boot 3.5.0**, and Boot-managed Spring for GraphQL. The example runs on in-memory services without a database, external APIs, or secrets. It provides a query returning multiple books whose authors are resolved through DataLoader.

### 5.1. Directory layout

```text
graphql-resolver-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/graphqltest/
    │   │   ├── GraphQlLabApplication.java
    │   │   ├── Book.java
    │   │   ├── Author.java
    │   │   ├── BookService.java
    │   │   ├── AuthorService.java
    │   │   ├── BookGraphQlController.java
    │   │   ├── AuthorLoaderConfiguration.java
    │   │   └── DemoTenantInterceptor.java
    │   └── resources/graphql/
    │       └── schema.graphqls
    └── test/
        └── java/com/example/graphqltest/
            ├── BookResolverSliceTest.java
            └── BookGraphQlHttpTest.java
```

Each `public` class/record sits in a matching file inside `package com.example.graphqltest`. Do not rename `graphql/schema.graphqls` to `schema.json`: Spring GraphQL loads SDL from resources under `classpath:graphql/**` by default.

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>graphql-resolver-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-graphql</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.graphql</groupId>
            <artifactId>spring-graphql-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**Why these dependencies?**

- `spring-boot-starter-graphql`: GraphQL Java, annotated controllers, `BatchLoaderRegistry`.
- `spring-boot-starter-web`: configures the app with Spring MVC HTTP transport.
- `spring-boot-starter-test`: JUnit Jupiter, Mockito, AssertJ, Spring Test/Boot testing.
- `spring-graphql-test`: `GraphQlTester`, `ExecutionGraphQlServiceTester`, `HttpGraphQlTester`.
- `spring-boot-starter-webflux` in `scope=test`: supplies `WebTestClient` so `HttpGraphQlTester` can test the MVC HTTP endpoint over a mock client. **Does not convert the production app to WebFlux**; with both MVC and WebFlux on the test classpath, Boot normally prioritizes Servlet MVC.

The Spring Boot parent aligns compatible dependency versions; omit explicit GraphQL Java/DataLoader versions in the sample POM to avoid conflicts.

### 5.3. GraphQL SDL contract

```graphql
# src/main/resources/graphql/schema.graphqls

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
  displayName: String!
}
```

**Contract:**

- `books` query returns a non-null list of non-null `Book` items.
- `Book.author` is nullable: a missing/unknown author **does not necessarily** null the whole books list. Changing the schema to `Author!` would allow errors/nulls to propagate upward.
- `id` has GraphQL type `ID!` and the Java sample uses `String`.
- `Book` carries an internal `authorId` field **not** declared in the schema; it is the key for DataLoader rather than a public field always exposed to clients.
- No SOAP/XML fields exist in the schema; GraphQL SDL uses its own type and field system.

### 5.4. Spring Boot application and records

```java
// src/main/java/com/example/graphqltest/GraphQlLabApplication.java
package com.example.graphqltest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GraphQlLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(GraphQlLabApplication.class, args);
    }
}
```

```java
// src/main/java/com/example/graphqltest/Book.java
package com.example.graphqltest;

public record Book(String id, String title, String authorId) {}
```

```java
// src/main/java/com/example/graphqltest/Author.java
package com.example.graphqltest;

public record Author(String id, String displayName) {}
```

Java records provide deterministic `equals`/`hashCode` and clean testing. They are not JPA entities. Sample values `team-a`/`team-b` only illustrate tenant context.

### 5.5. Two real services for the demo

```java
// src/main/java/com/example/graphqltest/BookService.java
package com.example.graphqltest;

import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class BookService {

    public List<Book> visibleBooks(String tenant) {
        if (tenant == null || tenant.isBlank()) {
            throw new IllegalArgumentException("Tenant is required");
        }
        return List.of(
                new Book("b-1", "GraphQL Essentials", "a-1"),
                new Book("b-2", "Spring Testing", "a-2"),
                new Book("b-3", "DataLoader Patterns", "a-1"));
    }
}
```

```java
// src/main/java/com/example/graphqltest/AuthorService.java
package com.example.graphqltest;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

import org.springframework.stereotype.Service;

@Service
public class AuthorService {

    public Map<String, Author> findByIds(
            Set<String> ids, String tenant) {
        if (tenant == null || tenant.isBlank()) {
            throw new IllegalArgumentException("Tenant is required");
        }
        Map<String, Author> result = new LinkedHashMap<>();
        for (String id : ids) {
            if (id.equals("a-1") || id.equals("a-2")) {
                result.put(id,
                        new Author(id, tenant + ":" + id));
            }
        }
        return result;
    }
}
```

Both services intentionally **make zero external calls** so full-context tests run offline. Author display names embed the tenant string so tests can verify per-request context propagation.

In a real app, `visibleBooks(tenant)` and `findByIds(ids,tenant)` must enforce principal authorization, tenant/resource scoping, and parameterized queries; **prefixing a display name is not data isolation**. Never ship this demo implementation as a production security mechanism.

### 5.6. Root and nested field resolvers

```java
// src/main/java/com/example/graphqltest/BookGraphQlController.java
package com.example.graphqltest;

import java.util.List;
import java.util.concurrent.CompletableFuture;

import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookGraphQlController {

    private final BookService bookService;

    public BookGraphQlController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(@ContextValue("tenant") String tenant) {
        return bookService.visibleBooks(tenant);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<String, Author> loader) {
        return loader.load(book.authorId());
    }
}
```

**Mechanics:**

- `@QueryMapping` maps `books` to root field `Query.books`.
- `@ContextValue("tenant")` reads the value from the execution's `GraphQLContext`; if missing when required, method argument resolution produces a GraphQL error.
- `@SchemaMapping(typeName="Book", field="author")` defines the field resolver, receiving `Book` as the source/parent object.
- `DataLoader<String,Author>` is resolved and injected by Spring GraphQL from the registry by key/value type; with `forTypePair(String.class, Author.class)` below, the default registered name corresponds to `Author.class.getName()`.
- The resolver returns `CompletableFuture<Author>` instead of calling `AuthorService.findByIds` per book. GraphQL Java coordinates batch dispatching.
- `Book.authorId` is the lookup key. Both b-1 and b-3 share a-1, so DataLoader can reuse its per-request cache.

**Never call `future.join()` inside the resolver itself**: blocking on a DataLoader future prior to dispatch can cause deadlock or break batching. Return the future to the GraphQL engine.

### 5.7. Registering a mapped DataLoader with request context access

```java
// src/main/java/com/example/graphqltest/AuthorLoaderConfiguration.java
package com.example.graphqltest;

import graphql.GraphQLContext;

import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
public class AuthorLoaderConfiguration {

    public AuthorLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(String.class, Author.class)
                .registerMappedBatchLoader((authorIds, env) -> {
                    GraphQLContext context = env.getContext();
                    String tenant = context.get("tenant");

                    if (tenant == null || tenant.isBlank()) {
                        return Mono.error(
                                new IllegalStateException(
                                        "Missing tenant context"));
                    }

                    return Mono.just(
                            authorService.findByIds(authorIds, tenant));
                });
    }
}
```

**Key points:**

1. `BatchLoaderRegistry` is a bean provided by the Spring for GraphQL starter. Configuration registers the loader **once at startup**, while Spring GraphQL creates/registers per-request DataLoader instances **for every GraphQL execution**.
2. `forTypePair(String.class, Author.class)` specifies key type `String` and value type `Author`. By default, the loader name is inferred from the value type's full class name; `@SchemaMapping` injects the matching `DataLoader<String,Author>`.
3. `registerMappedBatchLoader` receives the key set (`Set<String>`) and `BatchLoaderEnvironment`. It returns `Mono<Map<String,Author>>` to map keys to values.
4. `env.getContext()` is populated by Spring GraphQL with the execution's `GraphQLContext` via registry wiring. Read `tenant` **at batch dispatch time**, never capturing a single tenant in the singleton config constructor.
5. Check for null context to fail explicitly; never silently fall back to a default tenant.
6. Never store `GraphQLContext` or `DataLoader` in static fields or singleton caches; that risks mixing data across requests.

**Do not confuse contexts:** `BatchLoaderEnvironment#getContext()` from Java DataLoader carries whatever context object the registry wiring passes. Spring for GraphQL's `BatchLoaderRegistry` shares the execution's `GraphQLContext` with batch loaders automatically. If you construct a `DataLoaderRegistry` manually, you must configure the context provider yourself; having a `GraphQLContext` in the controller does not wire it automatically.

### 5.8. Transport interceptor simulating context creation

To test the HTTP → `GraphQLContext` path, the project defines an interceptor reading `X-Demo-Tenant`. It simulates context propagation for testing/demo only—**never use it for security**.

```java
// src/main/java/com/example/graphqltest/DemoTenantInterceptor.java
package com.example.graphqltest;

import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class DemoTenantInterceptor
        implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        String tenant = request.getHeaders()
                .getFirst("X-Demo-Tenant");

        if (tenant == null || tenant.isBlank()) {
            return Mono.error(new IllegalArgumentException(
                    "X-Demo-Tenant is required for demo"));
        }

        request.configureExecutionInput(
                (executionInput, builder) ->
                        builder.graphQLContext(context ->
                                context.put("tenant", tenant))
                                .build());

        return chain.next(request);
    }
}
```

**In the full HTTP test**, the header is set on the mock HTTP client, the interceptor places `tenant` into `GraphQLContext`, and both controller and loader read the same value.

**In `@GraphQlTest` via `ExecutionGraphQlServiceTester`**, there is no HTTP transport, so the interceptor does not run. The test sets context directly on `ExecutionInput`; that is not an improper workaround, it is deliberate boundary isolation.

An HTTP request missing the header in the demo rejects at transport via `Mono.error`, though the example defines no HTTP exception handler or status contract for that error. **Do not assert 401/403** from this demo interceptor. In a real application, Spring Security authenticates the request first, and `WebGraphQlInterceptor` reads trusted principals/claims into context cleanly.

## 6. Slice test: real resolvers, mocked services, real loader registration

This is the core of the lesson: `@GraphQlTest` starts no HTTP server; we test real GraphQL execution with mocked services and **real DataLoader registration**, while setting GraphQL context per request.

### 6.1. Why must loader configuration be imported?

`@GraphQlTest(BookGraphQlController.class)` is a slice: it does not auto-load every `@Configuration` or `@Service` in the application.

Therefore, in the test:

- `@MockitoBean BookService` provides the collaborator for `@QueryMapping`.
- `@MockitoBean AuthorService` provides the collaborator for the batch loader.
- `@Import(AuthorLoaderConfiguration.class)` loads the DataLoader registration config into the test's registry.
- `ExecutionGraphQlService` is the GraphQL execution infrastructure configured by the slice.
- `ExecutionGraphQlServiceTester.builder(service).configureExecutionInput(...)` lets the test supply `GraphQLContext` without HTTP.

Omitting `@Import` causes resolver injection of `DataLoader<String,Author>` to lack the registered loader. Mocking the DataLoader itself or calling Java controller methods directly skips real dispatch/mapping, defeating the goal.

### 6.2. `BookResolverSliceTest.java` — core test cases

```java
// src/test/java/com/example/graphqltest/BookResolverSliceTest.java
package com.example.graphqltest;

import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@GraphQlTest(BookGraphQlController.class)
@Import(AuthorLoaderConfiguration.class)
class BookResolverSliceTest {

    @Autowired
    ExecutionGraphQlService executionService;

    @MockitoBean
    BookService bookService;

    @MockitoBean
    AuthorService authorService;

    private ExecutionGraphQlServiceTester asTenant(String tenant) {
        return ExecutionGraphQlServiceTester
                .builder(executionService)
                .configureExecutionInput((input, builder) ->
                        builder.graphQLContext(context ->
                                context.put("tenant", tenant))
                                .build())
                .build();
    }

    private List<Book> books() {
        return List.of(
                new Book("b-1", "GraphQL Essentials", "a-1"),
                new Book("b-2", "Spring Testing", "a-2"),
                new Book("b-3", "DataLoader Patterns", "a-1"));
    }

    @Test
    void nestedAuthorResolverBatchesAndMapsByKey() {
        when(bookService.visibleBooks("team-a")).thenReturn(books());

        when(authorService.findByIds(
                Set.of("a-1", "a-2"), "team-a"))
                .thenReturn(Map.of(
                        "a-1", new Author("a-1", "team-a:Ada"),
                        "a-2", new Author("a-2", "team-a:Grace")));

        asTenant("team-a").document("""
                query {
                  books {
                    id
                    title
                    author { id displayName }
                  }
                }
                """)
                .execute()
                .path("books[0].title")
                .entity(String.class).isEqualTo("GraphQL Essentials")
                .path("books[0].author.displayName")
                .entity(String.class).isEqualTo("team-a:Ada")
                .path("books[1].author.id")
                .entity(String.class).isEqualTo("a-2")
                .path("books[1].author.displayName")
                .entity(String.class).isEqualTo("team-a:Grace")
                .path("books[2].author.displayName")
                .entity(String.class).isEqualTo("team-a:Ada");

        verify(bookService).visibleBooks("team-a");
        verify(authorService, times(1)).findByIds(
                Set.of("a-1", "a-2"), "team-a");
    }

    @Test
    void notSelectingAuthorDoesNotInvokeAuthorService() {
        when(bookService.visibleBooks("team-a")).thenReturn(books());

        asTenant("team-a").document("""
                { books { id title } }
                """)
                .execute()
                .path("books")
                .entityList(Map.class)
                .hasSize(3);

        verify(bookService).visibleBooks("team-a");
        verifyNoInteractions(authorService);
    }

    @Test
    void independentRequestsReceiveIndependentTenantContext() {
        when(bookService.visibleBooks("team-a")).thenReturn(books());
        when(bookService.visibleBooks("team-b")).thenReturn(books());

        when(authorService.findByIds(
                Set.of("a-1", "a-2"), "team-a"))
                .thenReturn(Map.of(
                        "a-1", new Author("a-1", "team-a:Ada"),
                        "a-2", new Author("a-2", "team-a:Grace")));

        when(authorService.findByIds(
                Set.of("a-1", "a-2"), "team-b"))
                .thenReturn(Map.of(
                        "a-1", new Author("a-1", "team-b:Ada"),
                        "a-2", new Author("a-2", "team-b:Grace")));

        String query = """
                { books { author { displayName } } }
                """;

        asTenant("team-a").document(query)
                .execute()
                .path("books[0].author.displayName")
                .entity(String.class).isEqualTo("team-a:Ada");

        asTenant("team-b").document(query)
                .execute()
                .path("books[0].author.displayName")
                .entity(String.class).isEqualTo("team-b:Ada");

        verify(authorService, times(1)).findByIds(
                Set.of("a-1", "a-2"), "team-a");
        verify(authorService, times(1)).findByIds(
                Set.of("a-1", "a-2"), "team-b");
    }

    @Test
    void missingContextMustNotSilentlyUseAnotherTenant() {
        ExecutionGraphQlServiceTester noTenant =
                ExecutionGraphQlServiceTester.create(
                        executionService);

        noTenant.document("""
                { books { id author { id } } }
                """)
                .execute()
                .errors()
                .satisfy(errors ->
                        assertThat(errors).isNotEmpty());

        verifyNoInteractions(bookService, authorService);
    }
}
```

**What these tests verify:**

1. `nestedAuthorResolverBatchesAndMapsByKey` guards **a query with 3 books and 2 distinct author IDs**, checking every output path and **a single batch service call** with `Set.of("a-1","a-2")`. This is a stronger signal than merely counting resolver invocations.
2. `notSelectingAuthorDoesNotInvokeAuthorService` guards selection-set semantics: when the client omits author, no author I/O occurs.
3. `independentRequestsReceiveIndependentTenantContext` guards against two consecutive GraphQL executions with identical keys reading cached authors from the prior tenant.
4. `missingContextMustNotSilentlyUseAnotherTenant` verifies GraphQL execution returns errors when the required `tenant` is missing rather than falling back to another tenant. Use `errors().satisfy(...)` to assert errors instead of calling `execute()` and reading data paths expecting no errors.

**Easily confused API details:**

- `@GraphQlTest` in Spring Boot 3.5 uses import `org.springframework.boot.test.autoconfigure.graphql.GraphQlTest`.
- `ExecutionGraphQlService` lives in `org.springframework.graphql.ExecutionGraphQlService`, whereas `ExecutionGraphQlServiceTester` lives in `org.springframework.graphql.test.tester`.
- `@MockitoBean` is Spring TestContext's bean override annotation; Mockito's `@Mock` **does not automatically** create a Spring bean.
- `GraphQlTester#path` is **relative to `data`**, so `"books[0].author.displayName"` has no `"data."` prefix.
- `errors().satisfy(...)` checks expected errors. When errors are unexpected, normal tests should fail instead of filtering all errors by default.
- Mockito mocks reset between test methods under default test config; do not rely on static mocks or counters across tests.

### 6.3. An important limit on asserting "one batch call"

When a document returns multiple books, the GraphQL engine may dispatch per execution level. In the sample query there is one `Book.author` level and 2 distinct keys, producing a single mapped batch call. However:

- Changing the query to add deeper nesting, aliases, or fragments with separate execution paths can increase dispatch counts.
- Setting a small `maxBatchSize` splits a dispatch into multiple calls.
- Duplicate batch function registration or clearing caches for the same key can trigger extra service calls.
- If `authorService` internally runs multiple SQL queries, one mapped batch call still does not prove the DB received a single query.

Therefore `times(1)` is a **scoped performance contract for this scenario**, not a universal theorem across all workloads. Use SQL observability/metrics or downstream call tracing when counting actual database round-trips.

## 7. HTTP integration test: from header through interceptor to loader

The slice test above **did not** execute `DemoTenantInterceptor` because there was no transport. To verify creating context from HTTP headers, use a full Spring Boot test with `HttpGraphQlTester` over mock HTTP (no TCP port required).

### 7.1. `BookGraphQlHttpTest.java`

```java
// src/test/java/com/example/graphqltest/BookGraphQlHttpTest.java
package com.example.graphqltest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureHttpGraphQlTester
class BookGraphQlHttpTest {

    @Autowired
    HttpGraphQlTester graphQlTester;

    private HttpGraphQlTester tenant(String name) {
        return graphQlTester.mutate()
                .webTestClient(client ->
                        client.defaultHeader(
                                "X-Demo-Tenant", name))
                .build();
    }

    @Test
    void httpHeaderReachesRootResolverAndBatchLoader() {
        tenant("team-a").document("""
                {
                  books {
                    id
                    title
                    author { id displayName }
                  }
                }
                """)
                .execute()
                .path("books[0].author.displayName")
                .entity(String.class).isEqualTo("team-a:a-1")
                .path("books[1].author.displayName")
                .entity(String.class).isEqualTo("team-a:a-2")
                .path("books[2].author.displayName")
                .entity(String.class).isEqualTo("team-a:a-1");
    }

    @Test
    void httpRequestsDoNotShareTenantCache() {
        String document = """
                { books { id author { displayName } } }
                """;

        tenant("team-a").document(document)
                .execute()
                .path("books[0].author.displayName")
                .entity(String.class).isEqualTo("team-a:a-1");

        tenant("team-b").document(document)
                .execute()
                .path("books[0].author.displayName")
                .entity(String.class).isEqualTo("team-b:a-1");
    }
}
```

**What this checks:**

- Spring Boot loads the **real** `BookService` and `AuthorService`, without Mockito mocks.
- The HTTP test client sends `X-Demo-Tenant` over the mock HTTP layer.
- `DemoTenantInterceptor` runs because the transport handler is active.
- `@ContextValue("tenant")` and the mapped loader read the matching tenant from `GraphQLContext`.
- `books[0]` and `books[2]` share author a-1 without picking up data from another tenant.
- Two requests with identical author IDs return display names scoped to their respective tenants.

**This is not network E2E:** `@SpringBootTest(MOCK)` with `@AutoConfigureHttpGraphQlTester` tests the HTTP handler inside a mock server context **without opening an embedded HTTP listener**. To test real sockets, use `RANDOM_PORT` with a matching tester; those tests must also manage ports, security, credentials, and infrastructure.

### 7.2. Test count and execution commands

The primary project has **6 JUnit test methods**: **4** in `BookResolverSliceTest` and **2** in `BookGraphQlHttpTest`. Run:

```bash
java -version
mvn -version

# Run both resolver slice and context transport tests:
mvn test

# Run each level individually:
mvn -Dtest=BookResolverSliceTest test
mvn -Dtest=BookGraphQlHttpTest test
```

Requires JDK 17+ and Maven, and may need Internet access to fetch initial dependencies. **There is no fixed stdout**: counts, ports, and logs vary by environment. What matters is that all test methods pass their assertions and Maven reports build success. No external database, broker, or cloud service is used in this project.

**Operational note:** If `spring-graphql-test` or the WebFlux test client dependency is missing, the testers will not compile or auto-configure. Inspect `pom.xml` and the dependency tree before converting a test into an HTTP socket test.

## 8. Advanced DataLoader: caching, dispatching, and batch mapping

### 8.1. Distinguishing batching from caching

**Batching** collects multiple keys *pending in an execution dispatch* and sends one batch call downstream. **Caching** remembers futures/results by key within a request so subsequent `load("a-1")` calls reuse them. The two usually work together, though each can be configured separately.

In the sample data:

```text
Books:
  b-1 → a-1
  b-2 → a-2
  b-3 → a-1

Resolver calls:
  loader.load("a-1")
  loader.load("a-2")
  loader.load("a-1")

Unique batch keys:
  {"a-1", "a-2"}

GraphQL output:
  b-1.author = Author a-1
  b-2.author = Author a-2
  b-3.author = Author a-1
```

If DataLoader caching is disabled, the loader may dispatch duplicate keys or behave differently depending on loader implementation. Do not test "exactly two keys" while ignoring cache configuration. If keys are mutable objects without stable `equals`/`hashCode`, caching and mapped results become unpredictable.

### 8.2. Why is `@BatchMapping` often simpler?

For straightforward `Book.author` associations, Spring for GraphQL supports:

```java
@Controller
class AlternativeBookController {
    private final AuthorService authorService;

    AlternativeBookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(
            List<Book> books,
            @ContextValue("tenant") String tenant) {

        Set<String> ids = books.stream()
                .map(Book::authorId)
                .collect(Collectors.toSet());

        Map<String, Author> byId =
                authorService.findByIds(ids, tenant);

        Map<Book, Author> result = new HashMap<>();
        for (Book book : books) {
            result.put(book, byId.get(book.authorId()));
        }
        return result;
    }
}
```

**This is an illustrative variant, not a file added to the main project.** To use it instead of an explicit DataLoader, import `Controller`, `BatchMapping`, `ContextValue`, `List`, `Map`, `Set`, `Collectors`, and `HashMap`. Never register both `@BatchMapping(Book.author)` and `@SchemaMapping(Book.author)` in the same application, as both claim the same GraphQL field.

`@BatchMapping` automatically creates a mapped batch loader and field data fetcher, eliminating `BatchLoaderRegistry`/`DataLoader.load` boilerplate in many scenarios. You can inject `@ContextValue` directly on the batch method. It fits cases that simply gather parent objects and fetch related entities. When you need `keyContexts`, custom cache settings, custom loader names, complex selection sets, or advanced policies, `BatchLoaderRegistry` offers more flexibility.

### 8.3. When to use an ordered loader instead of a mapped loader?

A batch service might return `List<Author>` for `List<String> keys`. In that case, the returned order **must match the input key order**; missing items must leave a corresponding null slot. With a mapped batch loader (`Set<K> → Map<K,V>`), entries are matched by key, making it safer when backends do not guarantee order.

When testing an ordered loader, **never only** assert `list.size()==n`. Intentionally return backend records out of order and verify that the adapter or lookup preserves the contract. For our mapped loader, the three-book test in section 6 checks exact pairing via `author.id` and `displayName`.

### 8.4. Testing a loader directly without running a GraphQL document

Spring for GraphQL also lets you register a `DefaultBatchLoaderRegistry` into a test `DataLoaderRegistry`, retrieve the loader by name, and call `load(...)` followed by `dispatchAndJoin()`. Pattern workflow:

```text
DefaultBatchLoaderRegistry registry
   │
   ├── forTypePair(...).registerMappedBatchLoader(...)
   │
   └── registerDataLoaders(dataLoaderRegistry, graphQLContext)
              │
              ▼
DataLoader<String, Author> loader
   │
   ├── load("a-1")
   ├── load("a-2")
   └── dispatchAndJoin()
              │
              ▼
Verify returned list/futures + authorService batch arguments
```

This illustrates the API flow rather than a standalone Java program. It works well when testing the **batch loader function**, caching, result mapping, and batch errors independently of SDL and field resolvers.

**However:** a passing loader unit test does not prove the GraphQL controller actually injects the matching loader name and type. Keep an integration test via `GraphQlTester` to confirm registration and field mapping.

### 8.5. Batch keys must carry enough context within a single request

Cross-request leakage is not the only danger. Even within **one** GraphQL request, if the same `authorId` is loaded under two different permissions or views, a DataLoader keyed solely by `authorId` can serve the wrong result. When context varies per parent or field, consider:

- Using a composite key `(tenantId,authorId,visibility)` with stable equality/hashCode.
- Using per-key context with `DataLoader.load(key, keyContext)` when needed, remembering that **`keyContext` does not automatically become part of the cache key**.
- Partitioning loaders by policy or deliberately disabling caching when a safe key is unavailable.
- Never treating a shared per-request context as blanket permission to return all fields; services must enforce resource-level checks.

## 9. GraphQL context: global context vs. local context

### 9.1. `GraphQLContext`

`GraphQLContext` is the execution-wide context read by data fetchers and batch loaders. `@ContextValue("tenant")` fetches keys from it. A `WebGraphQlInterceptor` populates attributes on `ExecutionInput` via `configureExecutionInput`.

In the project:

```java
request.configureExecutionInput(
        (executionInput, builder) ->
                builder.graphQLContext(context ->
                        context.put("tenant", tenant))
                        .build());
```

In a test without transport:

```java
ExecutionGraphQlServiceTester.builder(executionService)
        .configureExecutionInput((input, builder) ->
                builder.graphQLContext(context ->
                        context.put("tenant", "team-a"))
                        .build())
        .build();
```

**Never rely on `ThreadLocal` as the sole source of tenant** when resolvers, DataLoaders, or security checks can hop threads.

### 9.2. Local context

GraphQL Java supports `localContext` scoped to a specific branch/field rather than the whole request. Spring for GraphQL provides `@LocalContextValue` to read parent-field context in controller methods.

When a query contains multiple branches requiring distinct permissions or locales, do not keep overwriting one global context key. Consult `DataFetchingEnvironment`, local context, and per-key context documentation. Write tests using a document with **two sibling branches** to catch context bleed, rather than single-field queries.

**Note:** local context is not an automatic authentication mechanism. It is simply a data container that must be populated from a trusted source.

### 9.3. HTTP context differs from WebSocket/subscription context

HTTP GraphQL requests carry headers/cookies tied to a single HTTP exchange. WebSocket GraphQL subscriptions are long-lived, involving a handshake, `connection_init` payload, and multiple operations multiplexed on one connection. Auth propagation and token refresh/revocation lifecycles differ. Tests using `WebGraphQlInterceptor`/HTTP are insufficient to prove WebSocket auth works.

If the app supports subscriptions, use `WebSocketGraphQlTester` and test connect/auth/subscribe/stop/cancellation per contract rather than assuming `HttpGraphQlTester` covers subscriptions like standard queries.

## 10. GraphQL errors are not HTTP status codes

A GraphQL response typically has this shape:

```json
{
  "data": {
    "books": [
      {
        "id": "b-1",
        "author": null
      }
    ]
  },
  "errors": [
    {
      "message": "Access denied",
      "path": ["books", 0, "author"]
    }
  ]
}
```

This is an **illustration** of a partial data/error response. Real error messages, classifications, paths, and HTTP statuses depend on the GraphQL schema, handler, Spring GraphQL version, and error resolver; do not assume every permission failure produces this exact payload.

**QA rules:**

- A GraphQL field error can leave sibling data intact inside `data`; never assert HTTP 500 as the sole signal of failure.
- For non-null fields (`!`), errors/nulls can bubble up to parents and null out whole subtrees.
- `GraphQlTester` rejects unexpected errors by default; in happy-path tests, never filter or suppress all errors.
- When expecting errors intentionally, use `errors().expect(...)` or `errors().satisfy(...)`; distinguish "verified the expected error occurred" from "ignored errors to keep reading data."
- Never expose raw JDBC exceptions, tokens, or stack traces in production GraphQL error messages; implement a proper `DataFetcherExceptionResolver`/`@GraphQlExceptionHandler`.
- Assert GraphQL error paths and classifications when contractual; avoid locking assertions to unstable internal framework wording.

**Note on the missing-context test in section 6:** we asserted that `errors` is non-empty and the services were not called, without asserting exact framework message text that can vary across versions. When implementing HTTP 401/403 policies, add dedicated tests at the Spring Security/transport layer.

## 11. Test cases to include in a real project

| Test case | Tool | Core assertions |
| --- | --- | --- |
| Root query invokes business service | `@GraphQlTest + @MockitoBean` | Exact arguments and data paths |
| Field resolver returns nested entity | `GraphQlTester` | Each parent links to the right child key/value |
| N+1/batching | Real registry, mocked service | Exact batch calls/keys for the query shape |
| Cache reuse for same key within one request | GraphQL document with duplicate author IDs | No redundant downstream call; exact output |
| Cache isolation across two requests | Two executions with distinct contexts | No value reuse between tenant A and B |
| Missing/malformed context | Execution tester/transport tester | Error returned, no fallback to another tenant |
| Root query omits nested field | Minimal GraphQL selection set | `AuthorService` is never called |
| Principal/resource authorization | Security + service policy | User cannot read another tenant's data |
| Loader returns map missing a key | GraphQL response + nullable contract | Null/error matches schema |
| Batch service fails | `GraphQlTester` errors | No sensitive data leaked; proper partial data/nullability |
| Large selection set/complexity | Integration/performance test | Max depth/complexity guards, latency, batch sizing |
| HTTP header → context | `HttpGraphQlTester` | Interceptor ran, tenant/trace ID propagated |
| DataLoader `keyContexts`/`localContext` | Scenario with two sibling branches | No permission or filter bleed |
| SOAP endpoints in the same module | Spring-WS `MockWebServiceClient` | XML/SOAP payload, namespace, fault contract |

### 11.1. Verifying right behavior rather than merely counting calls

`verify(authorService, times(1)).findByIds(...)` is helpful for batch efficiency, yet **insufficient** if the returned map or tenant is wrong. Combine:

- Assert `books[0].author.id` and `books[1].author.id`/`displayName` in the response.
- Verify exact keys (distinct IDs) and tenant/context.
- Assert `AuthorService` is never invoked when the field is unselected.
- Run two requests with identical author keys and different tenants.
- Include negative cases (missing context, missing author, service failure).

Together, these assertions prove both **correct data** and **correct data-fetching behavior** for the tested query.

## 12. Common issues and fixes

### Error 1. `@GraphQlTest` does not create `BookService`

**Cause:** It is a GraphQL slice and does not auto-scan general `@Service` beans. **Fix:** declare `@MockitoBean BookService` or intentionally import the needed bean/config. Do not switch to `@SpringBootTest` just to fix one missing collaborator.

### Error 2. Loader bean exists, yet test complains DataLoader is missing

**Cause:** You imported `BookGraphQlController` without importing the configuration that registers it on `BatchLoaderRegistry`, or the loader name differs. **Fix:** `@Import(AuthorLoaderConfiguration.class)`; verify the loader name/type `Author.class.getName()` and generic `DataLoader<String,Author>`.

### Error 3. Creating a singleton DataLoader shared across all requests

**Consequence:** cross-request caching can leak data, especially when the same ID is viewed under different tenants or permissions. **Fix:** register a loader factory via `BatchLoaderRegistry` for proper per-request lifecycle; never retain a global `DataLoader` instance.

### Error 4. Resolver calls `join()`/`block()` right after `load`

**Consequence:** blocks before dispatch, risking deadlock, breaking batching, and blocking threads. **Fix:** return `CompletableFuture`/reactive types to the GraphQL engine; avoid blocking inside data fetchers wherever possible.

### Error 5. Batch returns results in database order for an ordered loader

**Consequence:** `a-1` might receive `a-2`'s data. **Fix:** ordered loaders must return lists aligned to input key order; mapped loaders return a Map keyed by ID. Assert specific field data, not only list size.

### Error 6. Using `@ContextValue` without providing context in a direct execution test

**Consequence:** GraphQL errors even though Spring Boot beans loaded properly. **Fix:** `ExecutionGraphQlServiceTester.builder(...).configureExecutionInput(...)`. Do not expect `WebGraphQlInterceptor` to populate context when using the direct tester, which bypasses interceptors.

### Error 7. Slice test passes, production HTTP still lacks context

**Consequence:** `@QueryMapping` fails with missing context over real HTTP. **Fix:** add `HttpGraphQlTester`/transport tests covering `WebGraphQlInterceptor` and real auth. Slice tests prove the resolver reads context, not that headers/tokens propagate.

### Error 8. Treating a request header as tenant authorization

**Consequence:** users forge the header to read another tenant's data. **Fix:** use authenticated identity, verified membership, and service-level authorization. The `X-Demo-Tenant` header in the example is strictly illustrative.

### Error 9. Checking only GraphQL JSON data while ignoring errors

**Consequence:** response returns partial data + errors yet tests read one field and treat the contract as successful. **Fix:** let `GraphQlTester` fail on unexpected errors; use `filter/expect/satisfy` only for anticipated errors with explicit assertions.

### Error 10. Mapped loader omits an author while schema declares `Author!`

**Consequence:** nullability propagation nulls `Book`/`books` more broadly than expected. **Fix:** decide whether "author required?" is part of the contract; test missing keys and error paths. Never assume every related object exists.

### Error 11. Slow tests / N+1 despite using DataLoader

**Cause:** loader dispatches across multiple execution levels, small `maxBatchSize`, caching disabled, custom schedulers, or the service running multiple DB queries. **Fix:** inspect traces/observations, captured SQL queries, batch sizes, keys, and query shapes rather than assuming N+1 is solved just because `DataLoader` is used.

### Error 12. Aliases or fragments corrupting the cache

**Cause:** a cache key holds only entity ID while output varies by field arguments, filters, locale, or auth visibility. **Fix:** include all result-affecting dimensions in composite keys or scope separate loaders; test two branches fetching the same ID under different contexts/arguments.

### Error 13. Mocks unexpectedly return null

**Cause:** Mockito was not stubbed for the exact `Set` of keys/tenant, or custom code passes different arguments. **Fix:** capture arguments/logical IDs, stub per contract, assert errors and expected paths. Avoid overly broad `any()` matchers when protecting tenant/key accuracy.

### Error 14. Auto-configuring HTTP tester without WebFlux test client

**Cause:** `HttpGraphQlTester` relies on `WebTestClient`, so MVC projects typically need `spring-boot-starter-webflux` in test scope. **Fix:** add dependencies per Spring Boot 3.5 docs and check the test context. Do not switch production to a WebFlux server just for the client.

### Error 15. Trying to test SOAP using `GraphQlTester`

**Cause:** confusing two mechanisms both casually called "resolvers/endpoints." SOAP uses XML envelopes, WSDL/XSD, `@Endpoint`, payload mapping, and faults. **Fix:** use Spring Web Services `MockWebServiceClient` and XML/XPath assertions for SOAP, keeping `GraphQlTester` for GraphQL documents/data/errors.

## 13. Quick comparison with SOAP in the same knowledge group

The parent group is "GraphQL and SOAP," while the topic "resolvers dependent on services, DataLoaders, and context" belongs to **GraphQL**. To avoid using the wrong tool:

| Aspect | GraphQL | SOAP/Spring-WS |
| --- | --- | --- |
| Interface description | GraphQL SDL (`.graphqls`) | WSDL/XSD |
| Execution unit | `@QueryMapping`, `@SchemaMapping`, field resolvers | `@Endpoint`, `@PayloadRoot`, `@RequestPayload` |
| Loading related data | `DataLoader`, `@BatchMapping` | Service calls per SOAP operation; no GraphQL-style DataLoader by default |
| Context | `GraphQLContext`, `@ContextValue`, Spring Security | SOAP headers, `MessageContext`, WS-Security/principal |
| Direct testing | `GraphQlTester`, `ExecutionGraphQlServiceTester` | `MockWebServiceClient` |
| Errors | `errors` in GraphQL response, possible partial data | SOAP Fault in SOAP Envelope |
| N+1 | Nested query can trigger multiple resolvers | Depends on service/operation design; not GraphQL field execution |

If a real system uses both SOAP and GraphQL, test adapters converting between them at the **service boundary**: a GraphQL resolver calling a mocked SOAP client via a mock HTTP/SOAP server; use Spring-WS testing specifically when verifying SOAP XML contracts. Never mix WSDL and SDL assertions in the same mismatched test.

## 14. Extensions: exceptions, performance, security, and concurrency

### 14.1. Batch service failures and partial data

Suppose `AuthorService` fails with a timeout. Options include:

- Converting it into a GraphQL error at `books[*].author`; if nullable, other book fields survive.
- Providing a policy-approved fallback/cached author while surfacing status if required by the business contract.
- Failing the entire query when author data is mandatory per schema/contract.

**Tests must lock in the policy.** Never write `errors().filter(error -> true)` across queries; it masks regressions. Use `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver` to classify errors cleanly without leaking stack traces or secrets.

### 14.2. Query complexity and resource budgeting

N+1 is one facet of GraphQL denial-of-service risk. Deeply nested queries, repeated aliases, and unbounded pagination can explode load keys, CPU, or memory. In production:

- Enforce depth/complexity limits, pagination bounds, and total requested nodes.
- Configure DataLoader `maxBatchSize` if downstream backends impose limits.
- Set timeouts and circuit breakers at downstream boundaries.
- Track batch counts, batch sizes, and latency via Micrometer Observations, traces, or structured logs.
- Distinguish per-request caches from distributed caches.
- Test bounded large queries via performance/integration tests; avoid brittle CPU-time microbenchmarks inside unit tests.

### 14.3. Security must reach the service layer

A GraphQL resolver can use `@PreAuthorize`, principals, or authenticated context, and field-level authorization is especially vital when queries traverse nested objects. **Never assume permitting a root query permits every nested field.** `AuthorService` must verify which author IDs the caller can see, or resolvers must enforce the matching policy.

When testing access denial:

- Identity A can view book b-1, yet cannot view author a-2.
- GraphQL response returns null/redacted/error per policy without leaking displayName.
- DataLoader batches must still preserve key/result alignment when some IDs are denied.
- Queries repeating the same key under two permission views within one request must prevent cache contamination.

### 14.4. ThreadLocal/Reactor Context vs. GraphQLContext

In Web MVC, security context often starts in a `ThreadLocal` on the request thread while GraphQL execution or async loaders hop threads. Spring for GraphQL provides context propagation support, yet custom executors or SDKs do not always preserve every context. In WebFlux, Reactor Context is distinct from `GraphQLContext` though they can be bridged/propagated.

**Never** grab a static `RequestContextHolder` inside a batch loader on a worker thread assuming the tenant is always present. Use the chosen context contract, proper identity/authorization, and test across asynchronous boundaries whenever the real app uses them.

### 14.5. Observing concurrent requests properly

Two HTTP requests can execute concurrently, each with its own `DataLoaderRegistry` and cache. If a real service uses an unsafe shared mutable map, a service concurrency bug can look like a DataLoader issue. Concurrency tests should use explicit latches/synchronization rather than `Thread.sleep`; assert both users/tenants receive accurate results regardless of completion order.

Each `GraphQlTester`/HTTP tester acts as a test client; calling `mutate()` adjusts headers on a separate client instance. That **does not** substitute for real authentication or prove backend cache isolation; test access control at the proper layer.

## 15. QA checklist for a DataLoader-backed resolver

- [ ] GraphQL SDL accurately defines root fields, nested fields, nullability, and types.
- [ ] `@QueryMapping` reads the right arguments/context and calls the right service.
- [ ] `@SchemaMapping` receives the parent object and loads the right key.
- [ ] `DataLoader` is registered via `BatchLoaderRegistry` with name/types matching the resolver.
- [ ] In slices, `@Import` loader configuration if outside component scan; mock services while keeping the loader real.
- [ ] Query tests include multiple parents and duplicate child keys to verify batching and caching.
- [ ] Assertions verify exact child ID/values per parent, not just item count.
- [ ] Batch key set and context are verified, not merely `times(1)`.
- [ ] Queries omitting the child field do not invoke the child's downstream service.
- [ ] Two GraphQL executions with identical keys and different tenants return isolated results.
- [ ] Missing context never silently falls back to a default tenant.
- [ ] HTTP tests verify interceptors place trusted request metadata into context.
- [ ] Unverified headers are never trusted as production authorization.
- [ ] DataLoader caches are not singleton/global and do not omit visibility dimensions from keys.
- [ ] Missing authors, service failures, and nullability/error paths are tested as required by business rules.
- [ ] No production secrets, tokens, or PII leak in GraphQL errors, logs, or test fixtures.
- [ ] Real-socket HTTP tests use `RANDOM_PORT` and isolated test resources/profiles.
- [ ] SOAP backends are tested with SOAP-specific tools for XML, WSDL, and faults.

## 16. Self-check questions

**Question 1.** Does a test calling `BookGraphQlController.author(book, mockDataLoader)` directly prove N+1 is solved?

**Answer:** No. It only proves the resolver calls `load(key)`. You need GraphQL execution with a real loader and multiple books, asserting batch keys/calls and JSON output.

**Question 2.** Does `@GraphQlTest` create the real `BookService`?

**Answer:** Not by default for a regular service outside the slice. Use `@MockitoBean` or explicitly import the collaborator.

**Question 3.** Why did the test need `@Import(AuthorLoaderConfiguration.class)`?

**Answer:** The loader configuration is a `@Configuration` excluded from the default component scan of a GraphQL slice; to test the real DataLoader, you must ensure it is loaded.

**Question 4.** A test has 3 books with author IDs `a-1,a-2,a-1`. How many unique keys are there?

**Answer:** Two: `a-1` and `a-2`. With DataLoader caching and batching in this scenario, the downstream batch receives a single set of two keys.

**Question 5.** Why does `GraphQlTester.path("books[0].author.id")` omit `data.`?

**Answer:** `GraphQlTester` paths are relative to the `data` section of the GraphQL response by default.

**Question 6.** Does `ExecutionGraphQlServiceTester` run `WebGraphQlInterceptor`?

**Answer:** No. It invokes the execution service directly, skipping transport handlers and interceptors. To test interceptors, use `WebGraphQlTester` or `HttpGraphQlTester` through the appropriate handler.

**Question 7.** Should a raw client `X-Tenant` header be passed straight to a service and treated as authorization?

**Answer:** No. You need a trusted identity, tenant/resource permission policies, and negative access-denial tests.

**Question 8.** If `author` is nullable in SDL and the batch loader cannot find one key, does the whole `books` list become null?

**Answer:** No. Nullable `Author` returns null for that specific parent. Only if the schema makes it non-null does GraphQL null propagation bubble up to parents/lists per `!`.

**Question 9.** How does a DataLoader named after `Author.class.getName()` differ from `BookService`?

**Answer:** DataLoader is the lookup/caching/batching facility for the author field; `BookService` provides root books. The loader's name and types must match what the resolver requests.

**Question 10.** Why aren't SOAP tests written with `GraphQlTester` despite sharing the same module?

**Answer:** SOAP uses XML Envelopes, WSDL, WS-Security, and SOAP Faults, tested with Spring-WS `MockWebServiceClient`; `GraphQlTester` executes GraphQL documents against an SDL schema.

## 17. Official references

- [Spring Boot 3.5 – Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.autoconfigured-graphql-tests): `@GraphQlTest`, Mockito beans, `GraphQlTester`, transport vs. direct execution.
- [Spring for GraphQL – Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html): `@QueryMapping`, `@SchemaMapping`, `@BatchMapping`, `@ContextValue`, `DataLoader` arguments.
- [Spring for GraphQL – Request Execution & Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html): `BatchLoaderRegistry`, per-request registries, context propagation, DataLoader batch testing.
- [Spring for GraphQL – Testing](https://docs.spring.io/spring-graphql/reference/testing.html): `GraphQlTester` variants, `ExecutionGraphQlServiceTester`, HTTP testers, error/path assertions.
- [Spring for GraphQL – Server Transports and Interceptors](https://docs.spring.io/spring-graphql/reference/transports.html): `WebGraphQlInterceptor`, `ExecutionInput` context.
- [GraphQL Java – DataLoader/Batching](https://graphql-java.com/documentation/batching/): dispatching, batching, per-request caching, key contexts.
- [Spring Web Services – Testing](https://docs.spring.io/spring-ws/docs/current/reference/html/#testing): `MockWebServiceClient` for SOAP endpoints (not applicable to GraphQL).

**Conclusion:** A correct resolver does more than return matching JSON. When it depends on services, DataLoaders, and context, the test suite should prove **per-field data, batched keys, downstream call counts for a given query shape, and context isolation across requests**. Use `@GraphQlTest` + mocked services + real loader registration for resolver logic; use `HttpGraphQlTester` to guard the HTTP/interceptor/context pipeline; and use service/security integration tests to prove real authorization and data isolation.