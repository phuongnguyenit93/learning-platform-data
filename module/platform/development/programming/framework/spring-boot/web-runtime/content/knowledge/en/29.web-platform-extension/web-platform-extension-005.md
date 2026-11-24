# GraphQL over HTTP and WebSocket in a Spring Boot Application

**GraphQL** is an API query language and **schema**-based execution runtime. Clients declare the exact fields to read in a `query`, request state changes via a `mutation`, or subscribe to continuous streams of results via a `subscription`. **GraphQL is not synonymous with WebSocket**: the exact same schema and resolvers can be served over **HTTP POST**, **WebSocket**, and in some implementations **Server-Sent Events (SSE)**. The transport determines how GraphQL operations reach the server and return results; the schema determines data structure and application access boundaries.

In Spring Boot 3.x, **Spring for GraphQL** builds on **GraphQL Java**. With Spring MVC, HTTP GraphQL typically lives at `POST /graphql`; WebSocket GraphQL must be enabled separately and requires the WebSocket starter. WebSocket is especially suited for `subscription`; ordinary `query`/`mutation` calls remain very well suited to HTTP POST, which is easier to observe, cache by design, and operate.

This lesson uses **Spring Boot 3.3.x, Java 17+, Spring MVC/Servlet, Spring for GraphQL 1.3.x, and Project Reactor** for illustration. It includes a project with **Query + Mutation over HTTP**, **Subscription over WebSocket**, a browser client, and tests. Note that Spring Boot 4.x/Spring GraphQL 2.x may rename starters/properties; do not copy configurations from a newer major version into a 3.x project without verifying them.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish **GraphQL schema/resolvers/operations** from **HTTP and WebSocket transports**.
- Write SDL schemas with `type Query`, `type Mutation`, `type Subscription`, non-null `!`, lists, and GraphQL input arguments.
- Write `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping`, and `@Argument` in Spring Boot.
- Send GraphQL HTTP requests via `POST /graphql` with JSON `query`, `variables`, and optional `operationName`.
- Read GraphQL responses containing `data`, `errors`, and `extensions`; understand why a GraphQL response with errors does not necessarily carry HTTP 500.
- Enable `spring.graphql.websocket.path` and implement WebSocket subscriptions using the `graphql-transport-ws` subprotocol.
- Distinguish `connection_init`, `connection_ack`, `subscribe`, `next`, `error`, `complete`, and `ping/pong`.
- Run a Java 17+ application with an in-memory book catalog and a subscription that emits events when books are added.
- Test using `curl`, the browser WebSocket API, and `@GraphQlTest`/`GraphQlTester`.
- Address security, CSRF/CORS/Origin, rate limits, query depth/complexity, N+1, WebSocket lifetime, reconnects, and multi-replica scaling.

## 2. Architectural Overview: Schema Is Independent of Transport

```text
                    Clients
               /                  \
     HTTP GraphQL POST          WebSocket GraphQL
        /graphql                  /graphql/ws
           |                           |
           v                           v
    GraphQlHttpHandler        GraphQlWebSocketHandler
           \                           /
            \                         /
              WebGraphQlHandler
                     |
              Interceptor chain
                     |
           GraphQL Java Execution
                     |
             Schema / DataFetchers
                     |
       @QueryMapping / @MutationMapping
                @SubscriptionMapping
                     |
       Business service / DB / event bus
```

In Spring Boot 3.3:

- The `spring-boot-starter-graphql` starter provides the schema/runtime infrastructure.
- The `spring-boot-starter-web` starter provides HTTP GraphQL over Spring MVC.
- The `spring-boot-starter-websocket` starter adds WebSocket support for Servlet apps; **merely adding the dependency does not enable the GraphQL WebSocket endpoint**.
- The `spring.graphql.websocket.path=/graphql/ws` property registers the WebSocket path for GraphQL.
- If you choose `spring-boot-starter-webflux`, HTTP and WebSocket can use the reactive stack without needing a separate WebSocket starter; that is a different runtime choice.
- A GraphQL `@Controller` is not a `@RestController` manually defining `@PostMapping("/graphql")`. Spring for GraphQL auto-configures HTTP/WS handlers, while controllers specify which **GraphQL fields** to resolve.

The key point: you do not write the logic for `books` or `bookAdded` twice for HTTP and WS. One schema and one set of DataFetchers suffice; the transport carries GraphQL operations to the runtime.

## 3. GraphQL Query, Mutation, and Subscription

| Operation | Purpose | Result Shape | Typical Transport |
| --- | --- | --- | --- |
| `query` | Read data per selection set | Typically one GraphQL execution result | HTTP POST |
| `mutation` | Request state changes | Typically one result, possibly with errors | HTTP POST |
| `subscription` | Subscribe to a stream of changing results over time | Multiple GraphQL results from a `Publisher` | WebSocket or SSE |
| GraphQL introspection | Inspect schema/type metadata | GraphQL query result | HTTP or WS if allowed |

**A mutation does not automatically push events to all clients.** For subscriptions to receive events, the server needs an event source connected to a GraphQL `Publisher`. The demo uses Reactor `Sinks.Many`; production can substitute Redis Streams, Kafka, RabbitMQ, or a suitable event service.

### 3.1. Selection Sets Let Clients Choose Fields

Example:

```graphql
query {
  books {
    id
    title
  }
}
```

The server returns only the fields the client requested according to the schema:

```json
{
  "data": {
    "books": [
      {"id": 1, "title": "Spring Boot"},
      {"id": 2, "title": "GraphQL Java"}
    ]
  }
}
```

This illustrates the output using sample data from the project below. If the client selects `category`, the result includes that field; if the client requests a field absent from the schema, the operation is invalid. You do not need separate endpoints `/books`, `/books/1`, and `/books/list-with-category` for each selection set.

### 3.2. Queries Differ from Mutations in Business Intent

Queries are expected to be read-only without observable side effects; mutations are used to modify data. However, **GraphQL does not automatically create database transactions** for resolvers, nor does it guarantee idempotency or full business rollback. Within the application, services must enforce authorization, validation, transactions, optimistic locking, and event emission per contract.

### 3.3. A Subscription Is a Sequence of Results

A subscription:

```graphql
subscription {
  bookAdded {
    id
    title
    category
  }
}
```

can emit sequentially:

```json
{"data":{"bookAdded":{"id":3,"title":"Spring Security","category":"Java"}}}
```

followed by another `data.bookAdded` for the next book, rather than returning a single JSON array. **Subscription is purely a GraphQL operation**, not tied to WebSocket at the schema level. Section 10 and Section 11 contrast WebSocket with SSE.

## 4. Schema SDL and Java Mapping

**Schema Definition Language (SDL)** is the public contract of a GraphQL API. It describes:

- Object type `Book` and its fields;
- Root `Query`/`Mutation`/`Subscription`;
- Built-in scalars `String`, `Int`, `ID`, `Boolean`, `Float`;
- Lists `[Book!]!`: non-null list containing non-null elements;
- Arguments `title: String!`: client must provide a non-null string.

Lesson example:

```graphql
type Query {
  books: [Book!]!
  bookById(id: Int!): Book
}

type Mutation {
  addBook(title: String!, category: String!): Book!
}

type Subscription {
  bookAdded: Book!
}

type Book {
  id: Int!
  title: String!
  category: String!
}
```

Spring Boot 3.3 by default discovers `.graphqls` or `.gqls` files under `src/main/resources/graphql/**`. It does not auto-generate the schema by scanning Java entity classes and inferring every field. Schema-first lets you review the API contract independently of storage.

**Why can `bookById` be null?** When no matching ID exists, the service returns `null` and the GraphQL contract allows this field to be empty. Conversely, `addBook: Book!` promises a `Book` when the mutation succeeds. When an error occurs on a non-null field, GraphQL's null propagation mechanism can turn the parent field null; clients should inspect both `data` and `errors`.

## 5. HTTP GraphQL: One URL, Many Operations

With Spring MVC, a GraphQL POST request typically looks like:

```http
POST /graphql HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/graphql-response+json

{
  "query": "query ($id: Int!) { bookById(id: $id) { id title } }",
  "variables": {"id": 1},
  "operationName": null
}
```

`query` is the GraphQL document string. `variables` is a JSON object containing typed variables; `operationName` is used when a document contains multiple operations or when the client wants to select a named operation. For a single simple query, `operationName` can be omitted. Note that HTTP GET GraphQL is not enabled by default on Boot 3.3 servers; the examples and standard contract use **POST**.

### 5.1. Returning Responses with data and errors

A valid response can look like:

```json
{
  "data": {
    "bookById": {"id": 1, "title": "Spring Boot"}
  }
}
```

When a field resolver fails, GraphQL can return **partial data** alongside an `errors` array:

```json
{
  "data": {
    "bookById": null
  },
  "errors": [
    {
      "message": "Internal error",
      "path": ["bookById"]
    }
  ]
}
```

This is a **shape example**, not a guarantee of the exact error message string at runtime. The GraphQL HTTP status depends on the media type and error category:

- Malformed HTTP/JSON or authentication failures can return 4xx/5xx.
- `application/graphql-response+json` responses have different HTTP status semantics than legacy `application/json`; GraphQL document parse/validation failures may return 4xx per spec.
- A resolver error during execution can appear inside `errors` even when the HTTP status is 200.

**Never treat `response.ok` as proof that every GraphQL field succeeded.** Clients must inspect `errors` and decide their own partial-data rendering policy. Likewise, do not blindly return HTTP 500 for every GraphQL validation error.

### 5.2. Why Variables Are Better Than String Concatenation

Avoid:

```javascript
const query = '{ bookById(id: ' + userInput + ') { title } }';
```

Concatenating raw input directly into GraphQL syntax can cause parse errors and alter query structure. Use a fixed query document and `variables`:

```json
{
  "query": "query Book($id: Int!) { bookById(id: $id) { title } }",
  "variables": {"id": 1}
}
```

Variables do not replace authorization or input validation, yet they cleanly separate syntax from data and make caching, monitoring, and persisted operations easier.

## 6. WebSocket GraphQL: A Different Protocol from Raw WebSocket

When using Spring for GraphQL WebSocket, the client cannot simply send a raw text frame `"hello"` expecting a resolver to run. It must speak the **GraphQL over WebSocket protocol**. Spring GraphQL uses the protocol defined by the **graphql-ws** library with subprotocol:

```text
graphql-transport-ws
```

Do not confuse it with the older **subscriptions-transport-ws** library, which used the subprotocol string `graphql-ws`. The naming is notoriously confusing:

| Library/protocol | Actual WebSocket subprotocol | Status |
| --- | --- | --- |
| Modern `graphql-ws` | `graphql-transport-ws` | Recommended with Spring GraphQL |
| Legacy `subscriptions-transport-ws` | `graphql-ws` | Legacy project, no longer preferred |
| Raw `WebSocket` text echo | No GraphQL subprotocol | Does not run GraphQL operations |

GraphQL WebSocket can carry single-result queries/mutations as well as multi-result subscriptions. Still, HTTP POST is usually more convenient for standard queries/mutations; WebSocket primarily solves event streaming, multiplexed subscriptions, and reduced round-trip overhead on an active channel.

### 6.1. WebSocket Handshake

A browser client connects:

```javascript
const ws = new WebSocket(
  "ws://localhost:8080/graphql/ws",
  "graphql-transport-ws"
);
```

In production over HTTPS, use `wss://`. On a successful HTTP/1.1 handshake, the status is typically `101 Switching Protocols` and the server selects `Sec-WebSocket-Protocol: graphql-transport-ws`. Once upgraded, GraphQL messages travel inside WebSocket frames instead of creating a new HTTP response per event.

### 6.2. Core Messages

```text
Client                                     Server
  |                                            |
  | WebSocket handshake graphql-transport-ws  |
  |------------------------------------------->|
  |<-------------------------------------------|
  |                                            |
  | {"type":"connection_init"}                 |
  |------------------------------------------->|
  | {"type":"connection_ack"}                  |
  |<-------------------------------------------|
  |                                            |
  | {"id":"sub-1","type":"subscribe",            |
  |  "payload":{"query":"subscription {...}"}} |
  |------------------------------------------->|
  |                                            |
  | {"id":"sub-1","type":"next",                 |
  |  "payload":{"data":{...}}}                  |
  |<-------------------------------------------|
  | {"id":"sub-1","type":"next", ...}            |
  |<-------------------------------------------|
  |                                            |
  | {"id":"sub-1","type":"complete"}             |
  |------------------------------------------->|
  |                                            |
  | close WebSocket when no longer needed      |
```

Meaning:

- `connection_init`: initializes the **GraphQL protocol connection** over the open socket. It can carry an authentication payload per application design, though unverified payloads must never be trusted.
- `connection_ack`: server accepts the GraphQL session on the socket; clients send `subscribe` only after ACK.
- `subscribe`: registers an operation with a unique `id` and `payload.query`/`variables`/`operationName`.
- `next`: one GraphQL execution result for that operation; `payload.data` and `payload.errors` may appear.
- `error`: operation-level error before/during execution per protocol; not an HTTP 500.
- `complete`: terminates the operation. Clients can proactively cancel a subscription; servers can also send `complete` when the stream ends.
- `ping`/`pong`: keepalive at the **GraphQL WebSocket message layer**, distinct from low-level WebSocket control Ping/Pong frames.

**Operation `id` is not a session ID or user ID.** One socket can multiplex multiple concurrent subscriptions using distinct IDs; response messages use `id` to route back to the right operation. Never reuse an ID while an existing operation is still active.

### 6.3. WebSocket Transport Does Not Guarantee Event Delivery

If a client drops offline, events emitted while disconnected are not replayed automatically. Upon reconnecting, the client must reopen the socket, `connection_init`, re-authenticate, and send a new `subscribe`. To recover missed events, the schema needs cursors/sequences backed by a durable event store. `graphql-transport-ws` does not build database replay or exactly-once guarantees.

## 7. Complete Project: Spring Boot MVC + GraphQL HTTP + WebSocket

Demo managing a simple book catalog:

- Two books preloaded in memory.
- `books` returns the list sorted by ID.
- `bookById` looks up one book.
- `addBook` adds a book and emits an event.
- `bookAdded` streams books added **after the client subscribes**.
- An HTML client uses `fetch` for Query/Mutation and WebSocket for Subscription.

In-memory data is **lost on JVM restart**. The event sink is **best-effort with no replay**, unsuitable for guaranteed notification delivery. This is intentional so the lesson stays focused on GraphQL transports.

### 7.1. Initializing from Spring Initializr

Choose Java 17+, Spring Boot **3.3.x**, Gradle/Groovy, and dependencies **Spring for GraphQL**, **Spring Web**, and **WebSocket**.

Initializr-generated `build.gradle` dependencies block:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-websocket'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.graphql:spring-graphql-test'
}
```

This is a **dependencies snippet**; running requires Gradle plugins, repositories, Boot version/dependency management, and the Initializr wrapper. Do not pin a different GraphQL Java or Reactor version outside the BOM without good reason. `spring-boot-starter-graphql` already brings in the GraphQL/Reactor infrastructure needed for `Flux`/`Sinks` in the demo; do not add `spring-boot-starter-webflux` solely for WebSocket when the project uses Servlet MVC.

Structure:

```text
src/
  main/
    java/demo/
      GraphQlTransportApplication.java
      Book.java
      CatalogStore.java
      CatalogGraphQlController.java
    resources/
      graphql/schema.graphqls
      application.properties
      static/index.html
  test/
    java/demo/
      CatalogGraphQlTest.java
```

### 7.2. SDL: schema.graphqls

Create `src/main/resources/graphql/schema.graphqls`:

```graphql
type Query {
  books: [Book!]!
  bookById(id: Int!): Book
}

type Mutation {
  addBook(title: String!, category: String!): Book!
}

type Subscription {
  bookAdded: Book!
}

type Book {
  id: Int!
  title: String!
  category: String!
}
```

Spring Boot searches for schemas under `classpath:graphql/**/` matching `.graphqls`/`.gqls` by default. Renaming the file to `schema.txt` or placing it outside resources without configuring locations prevents automatic discovery. The schema uses `Int` for IDs in the demo, bounded to 32-bit GraphQL integers; production typically prefers `ID` or UUID strings since database identities are not necessarily 32-bit ints.

### 7.3. Application Class

`src/main/java/demo/GraphQlTransportApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GraphQlTransportApplication {
    public static void main(String[] args) {
        SpringApplication.run(GraphQlTransportApplication.class, args);
    }
}
```

The application scans package `demo`; you do not write a `@PostMapping("/graphql")` manually. Spring Boot + Spring for GraphQL register transport handlers and wire `@Controller` resolvers.

### 7.4. Book Record

`src/main/java/demo/Book.java`:

```java
package demo;

public record Book(int id, String title, String category) {
}
```

GraphQL Java can read fields from Java record accessors (`id()`, `title()`, `category()`) via property fetchers. Java classes and GraphQL types do not have to share identical names in every app, though matching them keeps the demo clear. You do not need JPA entities/DTOs immediately when learning GraphQL resolver mapping.

### 7.5. CatalogStore: Data and Event Sink

`src/main/java/demo/CatalogStore.java`:

```java
package demo;

import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@Service
public class CatalogStore {

    private final ConcurrentMap<Integer, Book> books =
            new ConcurrentHashMap<>();

    private final AtomicInteger sequence = new AtomicInteger(2);

    private final Sinks.Many<Book> addedEvents =
            Sinks.many().multicast().directBestEffort();

    public CatalogStore() {
        books.put(1, new Book(1, "Spring Boot", "Java"));
        books.put(2, new Book(2, "GraphQL Java", "API"));
    }

    public List<Book> list() {
        return books.values().stream()
                .sorted(Comparator.comparingInt(Book::id))
                .toList();
    }

    public Book find(int id) {
        return books.get(id);
    }

    public Book add(String title, String category) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title must not be blank");
        }
        if (category == null || category.isBlank()) {
            throw new IllegalArgumentException("category must not be blank");
        }

        Book created = new Book(
                sequence.incrementAndGet(),
                title.strip(),
                category.strip());

        books.put(created.id(), created);

        // Best effort: events are not persisted for replay.
        addedEvents.tryEmitNext(created);

        return created;
    }

    public Flux<Book> subscribeToAdditions() {
        return addedEvents.asFlux();
    }
}
```

**Technical explanation:**

1. `ConcurrentHashMap` and `AtomicInteger` avoid basic race conditions across concurrent demo requests. They **do not replace transactions, uniqueness constraints, or a database**.
2. `list()` sorts by ID so query results have deterministic ordering; a Java `Map` does not guarantee list order.
3. `addedEvents` is a multicast `Sinks.Many` for multiple subscribers. `directBestEffort()` **does not replay** events to late subscribers; if there are no subscribers, `tryEmitNext` drops the event. If a subscriber is too slow, events can be dropped. This is an illustrative **best-effort** model without a delivery SLA.
4. `add()` stores the `Book` and then attempts to emit the event. A mutation can succeed even with zero WebSocket clients connected; that is correct for saving books. However, it can also create a **race** if a client just opened a subscription and the mutation fires before registration completes.
5. In production, when durable events are required, consider **transactional outbox** or an event log/broker with dedup/replay; do not simply swap `Sinks.Many` for a queue while ignoring transaction-then-publish atomicity.
6. Never store `WebSocketSession` directly in this service: the GraphQL runtime manages the transport; the service simply returns `Flux<Book>`.

`tryEmitNext` can return `FAIL_ZERO_SUBSCRIBER` or `FAIL_OVERFLOW`. In the demo, the result is ignored because "adding a book" does not depend on anyone listening. In systems requiring guaranteed event delivery, **never ignore this result**; design durable delivery instead.

### 7.6. CatalogGraphQlController: One Resolver for Multiple Transports

`src/main/java/demo/CatalogGraphQlController.java`:

```java
package demo;

import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;

@Controller
public class CatalogGraphQlController {

    private final CatalogStore store;

    public CatalogGraphQlController(CatalogStore store) {
        this.store = store;
    }

    @QueryMapping
    public List<Book> books() {
        return store.list();
    }

    @QueryMapping
    public Book bookById(@Argument("id") int id) {
        return store.find(id);
    }

    @MutationMapping
    public Book addBook(
            @Argument("title") String title,
            @Argument("category") String category) {

        return store.add(title, category);
    }

    @SubscriptionMapping
    public Flux<Book> bookAdded() {
        return store.subscribeToAdditions();
    }
}
```

Method names match schema fields:

| Java annotation/method | GraphQL field | Meaning |
| --- | --- | --- |
| `@QueryMapping books()` | `Query.books` | List resolver |
| `@QueryMapping bookById(...)` | `Query.bookById` | Lookup by ID resolver |
| `@MutationMapping addBook(...)` | `Mutation.addBook` | Create book + attempt event emit |
| `@SubscriptionMapping bookAdded()` | `Subscription.bookAdded` | Returns `Publisher`/`Flux` for events |

`@Argument("title")` extracts the GraphQL argument and binds it to the Java type. Specifying the name explicitly avoids depending on compiler parameter-name metadata. If schema field `addBook` is renamed to `createBook` while keeping the old Java method name, update `@MutationMapping(name="createBook")` or rename the method so mapping stays valid.

**Do not use `@GetMapping("/graphql")`**, and do not return `ResponseEntity<Book>` from `@QueryMapping` like a REST endpoint. The GraphQL execution engine invokes DataFetchers, selects fields, produces `data/errors`, and manages GraphQL types.

### 7.7. application.properties

`src/main/resources/application.properties`:

```properties
server.port=8080

# Spring Boot 3.3 HTTP GraphQL: defaults to /graphql.
spring.graphql.path=/graphql

# WebSocket GraphQL is OFF by default; must declare path to enable.
spring.graphql.websocket.path=/graphql/ws

# Require client to initialize protocol promptly.
spring.graphql.websocket.connection-init-timeout=20s

# Ping GraphQL WebSocket if channel stays idle long enough.
spring.graphql.websocket.keep-alive=20s

# Local learning only. Enable GraphiQL in dev environment.
spring.graphql.graphiql.enabled=true

# Do not expose schema printer endpoint in the example.
spring.graphql.schema.printer.enabled=false
```

Notes:

- **`spring.graphql.path`** is the HTTP endpoint property in **Boot 3.3**. In newer major versions, property paths may change; do not substitute Boot 4 docs directly.
- **`spring.graphql.websocket.path`** is not enabled by default; only when both `spring-boot-starter-websocket` and this property are present does Boot expose the GraphQL WS endpoint.
- **GraphiQL** is a dev tool for testing queries/mutations; in production, disable it or protect it via authentication/network controls. It **does not replace API security**.
- **`keep-alive`** sends periodic pings when idle per Spring GraphQL 1.3/Boot 3.3; NGINX/CDNs still enforce their own timeouts. No setting preserves a socket across a JVM restart.

### 7.8. Simple Browser Client Without External JS Libraries

Create `src/main/resources/static/index.html`. This page connects to the same origin, so the demo needs no CORS or cross-site cookie configuration. It uses the browser's native `WebSocket` and manually sends `graphql-transport-ws` messages so the protocol is transparent. In larger apps, use an official compatible client like `graphql-ws` for complete reconnect, ping/pong, multiplexing, and error handling.

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>GraphQL HTTP and WebSocket</title>
</head>
<body>
  <h1>GraphQL Book Catalog</h1>

  <button id="query">Load books (HTTP)</button>
  <button id="subscribe">Subscribe bookAdded (WS)</button>

  <input id="title" value="Spring Security" aria-label="Book title">
  <input id="category" value="Java" aria-label="Book category">

  <button id="mutate">Add book (HTTP)</button>
  <button id="disconnect">Disconnect WebSocket</button>

  <pre id="log"></pre>

  <script>
    const logElement = document.querySelector("#log");
    const log = (text) => {
      logElement.textContent += text + "\n";
    };

    let socket = null;
    const operationId = "books-live-1";

    async function graphql(query, variables = {}) {
      const response = await fetch("/graphql", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/graphql-response+json"
        },
        body: JSON.stringify({query, variables}),
        cache: "no-store"
      });

      const result = await response.json();

      if (!response.ok || result.errors?.length) {
        throw new Error(
          JSON.stringify({
            status: response.status,
            errors: result.errors || []
          })
        );
      }
      return result.data;
    }

    document.querySelector("#query").onclick = async () => {
      try {
        const data = await graphql(
          "{ books { id title category } }"
        );
        log("QUERY: " + JSON.stringify(data));
      } catch (error) {
        log("QUERY ERROR: " + error.message);
      }
    };

    document.querySelector("#mutate").onclick = async () => {
      try {
        const title = document.querySelector("#title").value;
        const category = document.querySelector("#category").value;

        const data = await graphql(
          "mutation CreateBook($title: String!, " +
          "$category: String!) { " +
          "addBook(title: $title, category: $category) " +
          "{ id title category } }",
          {title, category}
        );

        log("MUTATION: " + JSON.stringify(data));
      } catch (error) {
        log("MUTATION ERROR: " + error.message);
      }
    };

    document.querySelector("#subscribe").onclick = () => {
      if (socket && socket.readyState !== WebSocket.CLOSED) {
        log("WebSocket already exists; disconnect before opening a new one");
        return;
      }

      const scheme =
        location.protocol === "https:" ? "wss:" : "ws:";
      const url = scheme + "//" + location.host + "/graphql/ws";

      socket = new WebSocket(url, "graphql-transport-ws");

      socket.onopen = () => {
        log("WS OPEN: " + socket.protocol);
        socket.send(JSON.stringify({
          type: "connection_init"
        }));
      };

      socket.onmessage = (event) => {
        const message = JSON.parse(event.data);

        if (message.type === "connection_ack") {
          log("WS connection_ack");
          socket.send(JSON.stringify({
            id: operationId,
            type: "subscribe",
            payload: {
              query:
                "subscription { bookAdded " +
                "{ id title category } }"
            }
          }));
          log("WS subscribe sent");
        } else if (message.type === "next") {
          log("WS NEXT: " +
              JSON.stringify(message.payload));
        } else if (message.type === "error") {
          log("WS operation ERROR: " +
              JSON.stringify(message.payload));
        } else if (message.type === "complete") {
          log("WS operation complete: " + message.id);
        } else if (message.type === "ping") {
          socket.send(JSON.stringify({
            type: "pong",
            payload: message.payload
          }));
        } else if (message.type === "pong") {
          log("WS pong");
        }
      };

      socket.onerror = () => log("WS transport error");
      socket.onclose = (event) => {
        log("WS CLOSED code=" + event.code);
      };
    };

    document.querySelector("#disconnect").onclick = () => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
          id: operationId,
          type: "complete"
        }));
        socket.close(1000, "user closed");
      }
    };
  </script>
</body>
</html>
```

**How to test in the browser:**

1. Open `http://localhost:8080/`.
2. Click **Load books (HTTP)**: the browser POSTs `/graphql` and receives the two initial books.
3. Click **Subscribe bookAdded (WS)**: the browser opens `ws://localhost:8080/graphql/ws` with the exact subprotocol, sends `connection_init`, waits for `connection_ack`, and sends `subscribe`.
4. Once the log shows `WS subscribe sent`, give the server a moment to register the subscription (usually very quick), then click **Add book (HTTP)**.
5. The HTTP mutation adds the book, while the WebSocket receives `next` with the new `Book` payload.
6. Click **Disconnect WebSocket** to cancel the subscription and close the socket.

**Because the event sink is best-effort with no delivery guarantee:** if a mutation happens before the subscriber actually registers, or if a subscriber is too slow, `WS NEXT` may not appear. Verify by opening subscribe first, waiting briefly, and then mutating. This is a good opportunity to see the difference between a live event stream and a durable event log.

The page uses `textContent` instead of `innerHTML` so server/user strings are not rendered as executable markup. In production, still validate input, enforce permissions, and defend against XSS application-wide.

### 7.9. Running the Project

From the folder containing the Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

You cannot compile Spring files with a bare `javac CatalogStore.java` without the dependency classpath. Gradle Wrapper + Spring Boot plugins download and compile matching GraphQL/Spring/Reactor versions.

Once the app starts, open:

```text
http://localhost:8080/
http://localhost:8080/graphiql
```

`/graphiql` is enabled strictly for local dev per the property. If the app fails to start, check schema parse errors, field mapping mismatches, incompatible dependencies, port 8080 in use, or missing WebSocket starter.

## 8. Testing Queries over HTTP

### 8.1. List Query

```bash
curl -sS -X POST http://localhost:8080/graphql \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/graphql-response+json' \
  --data '{"query":"{ books { id title category } }"}'
```

Expected body before any mutations:

```json
{
  "data": {
    "books": [
      {"id": 1, "title": "Spring Boot", "category": "Java"},
      {"id": 2, "title": "GraphQL Java", "category": "API"}
    ]
  }
}
```

Whitespace and JSON object property order are not guaranteed; the data and book ordering from the service sort are what to verify.

### 8.2. Query with Variables

```bash
curl -sS -X POST http://localhost:8080/graphql \
  -H 'Content-Type: application/json' \
  --data '{"query":"query FindBook($id:Int!){bookById(id:$id){id title}}","variables":{"id":1}}'
```

Equivalent result:

```json
{"data":{"bookById":{"id":1,"title":"Spring Boot"}}}
```

When `id` does not exist, the resolver returns `null`, matching SDL `bookById(...): Book`:

```json
{"data":{"bookById":null}}
```

This does not require a separate HTTP 404 for a missing ID; in GraphQL, "entity not found" is commonly expressed via a nullable field and the schema contract. If business rules want a dedicated error code, use `GraphQLError`/`DataFetcherExceptionResolver` and agree on it with clients.

### 8.3. On PowerShell

PowerShell can use `curl.exe` and quotes double-quoted strings differently from Bash. A clean way to avoid long escaping is creating `query.json` containing:

```json
{
  "query": "query FindBook($id:Int!) { bookById(id:$id) { id title } }",
  "variables": {"id": 1}
}
```

Then:

```powershell
curl.exe -sS -X POST http://localhost:8080/graphql -H "Content-Type: application/json" --data-binary "@query.json"
```

Creating a JSON request file is not needed in the Java app; it is just a terminal testing convenience. When testing with real Bearer tokens or cookies, never put credentials in committed files.

## 9. Testing Mutations over HTTP

### 9.1. Adding a Book

```bash
curl -sS -X POST http://localhost:8080/graphql \
  -H 'Content-Type: application/json' \
  --data '{"query":"mutation Add($title:String!,$category:String!){addBook(title:$title,category:$category){id title category}}","variables":{"title":"Spring Security","category":"Java"}}'
```

If no prior mutations ran, the response is typically:

```json
{
  "data": {
    "addBook": {
      "id": 3,
      "title": "Spring Security",
      "category": "Java"
    }
  }
}
```

An HTTP GraphQL mutation sends one request and receives one JSON response. If any WebSocket subscriber is active, the service simultaneously tries to emit the new `Book` to the sink. **A successful mutation does not guarantee all subscribers received the event.**

### 9.2. After the Mutation, Query Returns the Added Item

```bash
curl -sS -X POST http://localhost:8080/graphql \
  -H 'Content-Type: application/json' \
  --data '{"query":"{ books { id title } }"}'
```

The list now includes the newly created book because data resides in memory inside the same JVM. Upon restart, the store constructor initializes only the original two books; this is not a durable database.

### 9.3. GraphQL Validation Errors

If the client requests a field absent from the SDL:

```bash
curl -i -X POST http://localhost:8080/graphql \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/graphql-response+json' \
  --data '{"query":"{ books { unknownField } }"}'
```

The GraphQL engine must report a validation error rather than returning `unknownField`. In GraphQL over HTTP with `application/graphql-response+json`, error categories can affect HTTP status codes. Inspect **both the status and the `errors` array**, without hardcoding one exact body/error message across every Spring GraphQL version.

### 9.4. Different Categories of Errors

- Request body is not valid JSON: HTTP transport error.
- Query field missing from schema: GraphQL parse/validation error.
- Null `title` for schema `String!`: validation/coercion error before calling the resolver.
- Empty/whitespace `title`: GraphQL `String!` **does not reject empty strings automatically**; the demo `CatalogStore` throws `IllegalArgumentException`, which Spring GraphQL can convert into a GraphQL error.
- Insufficient permissions to read a book: authorization/field policy error designed by the application.
- Database or downstream timeout: service error requiring safe handling/mapping.

Never return raw SQL exceptions, stack traces, tokens, or internal hosts to clients. Spring GraphQL provides `DataFetcherExceptionResolver` to control GraphQL errors emitted from resolvers.

## 10. Testing Subscriptions over WebSocket

### 10.1. Sequence of Steps

1. Open the demo HTML page.
2. Click to subscribe via WebSocket and wait for `connection_ack`.
3. The server receives `subscribe` for `bookAdded` and creates a GraphQL subscription execution.
4. In the same or another tab, send an HTTP mutation to add a book.
5. The subscriber receives a `next` message with `payload.data.bookAdded` if the event occurred after the subscription was actively registered.
6. Close the connection or send `complete` when done.

This demonstrates that **Query/Mutation use HTTP and Subscription uses WebSocket, yet both share the same service/resolvers**.

### 10.2. Real Message Shapes

Client sends immediately after the WebSocket handshake:

```json
{"type":"connection_init"}
```

Server replies:

```json
{"type":"connection_ack"}
```

Client sends subscription:

```json
{
  "id": "books-live-1",
  "type": "subscribe",
  "payload": {
    "query": "subscription { bookAdded { id title category } }"
  }
}
```

Once the mutation runs and the sink emits successfully, the server returns an **equivalent** message:

```json
{
  "id": "books-live-1",
  "type": "next",
  "payload": {
    "data": {
      "bookAdded": {
        "id": 3,
        "title": "Spring Security",
        "category": "Java"
      }
    }
  }
}
```

This illustrates the GraphQL WS protocol format. `extensions`, JSON key order, and extra fields may vary; do not parse by matching raw literal strings. Long-lived operations can emit **many `next` frames** and only terminate with `complete` on unsubscribe or stream completion.

### 10.3. curl Alone Is Not Enough

`curl -i http://localhost:8080/graphql/ws` is not a valid WebSocket GraphQL client. WebSocket requires an upgrade handshake and subprotocol, followed by JSON protocol messages inside WebSocket frames. Use HTML `new WebSocket(url, "graphql-transport-ws")` from the demo or a library/CLI supporting the subprotocol. A generic WebSocket tool will not send `connection_init`/`subscribe` unless you send them explicitly.

### 10.4. Why Might 101 Succeed Yet No Events Arrive?

The WebSocket handshake may succeed while:

- The client did not negotiate `graphql-transport-ws`.
- `connection_init` was never sent or arrived too late, hitting the connection-init timeout.
- The client sent `subscribe` without waiting for `connection_ack`.
- `payload.query` is not a valid GraphQL subscription.
- The mutation occurred **before** the subscriber actually connected.
- Zero subscribers / slow subscriber caused `Sinks.directBestEffort` to drop the event.
- A proxy terminated the connection due to idle timeout or expired auth token.
- You used the legacy `subscriptions-transport-ws` protocol sending `GQL_START` messages, which modern Spring GraphQL does not handle that way.

Inspect Network → WS Messages/Frames in browser DevTools and server logs; do not stop at checking HTTP 101.

## 11. Subscriptions over SSE: An HTTP Option Without WebSocket

Spring for GraphQL 1.3 supports **GraphQL subscriptions over Server-Sent Events** on the HTTP endpoint. When a client sends a GraphQL subscription via **HTTP POST** with a JSON request body and header `Accept: text/event-stream`, the HTTP GraphQL transport can return an SSE stream.

Example in a first terminal:

```bash
curl -N -sS -X POST http://localhost:8080/graphql \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  --data '{"query":"subscription { bookAdded { id title category } }"}'
```

Keep it running and send a mutation from a second terminal as in Section 9.1. When an event arrives, the initial response carries `Content-Type: text/event-stream`, followed by SSE records containing GraphQL results per GraphQL-over-SSE. **Do not guess exact raw line-by-line SSE formatting for every Spring GraphQL version**; verify the client parses equivalent GraphQL results.

**Important:** the browser's native `EventSource` typically opens a **GET** request and cannot send arbitrary POST bodies or `Authorization` headers. Since Spring GraphQL's SSE server endpoint here relies on **POST + JSON body + Accept**, you cannot replace that `curl` call with just:

```javascript
new EventSource("/graphql");
```

For browser clients using GraphQL over SSE POST, use a `fetch` streaming reader or a GraphQL SSE client library supporting "distinct connections" and the right media type. Do not confuse GraphQL-over-SSE with an arbitrary `GET /events` SSE endpoint.

### 11.1. When to Choose SSE vs. WebSocket for Subscriptions?

| Need | SSE/HTTP POST | WebSocket |
| --- | --- | --- |
| Receiving events from server only | Suitable | Suitable |
| Client sends commands frequently on the same channel | Requires separate HTTP requests | Can multiplex messages/operations |
| HTTP-centric proxies | Often simpler | Must support WS handshake and idle timeouts |
| Native browser API without library | Needs `fetch` streaming for GraphQL POST SSE | Has `WebSocket`, though GraphQL WS messages must be implemented |
| Many concurrent subscriptions/channels | Many HTTP streams can consume resources | One socket can multiplex operations |
| Reconnect/replay | Not guaranteed; app must design it | Not guaranteed; app must design it |
| Auth via custom headers | HTTP POST clients can attach headers | Browser `WebSocket` cannot attach arbitrary `Authorization` headers in handshake |
| Connection complexity | Usually less stateful | Requires init/ack/ping/complete/reconnect |

Supporting multiple transports in Spring GraphQL does not mean all of them should be enabled in production. Choose based on client libraries, infrastructure, requirements, and operational readiness.

## 12. Testing with @GraphQlTest and GraphQlTester

Spring Boot 3.3 provides `@GraphQlTest` to test **schema/resolvers** without starting an HTTP server or WebSocket listener. Add the dependency:

```groovy
testImplementation 'org.springframework.graphql:spring-graphql-test'
```

It is already in `build.gradle` from Section 7.1. Create `src/test/java/demo/CatalogGraphQlTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest(CatalogGraphQlController.class)
@Import(CatalogStore.class)
class CatalogGraphQlTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void readsBookById() {
        graphQlTester
                .document("{ bookById(id: 1) { title } }")
                .execute()
                .path("bookById.title")
                .entity(String.class)
                .isEqualTo("Spring Boot");
    }

    @Test
    void addsBookThroughMutation() {
        graphQlTester
                .document("""
                    mutation Add($title:String!,$category:String!) {
                      addBook(title:$title,category:$category) {
                        title
                        category
                      }
                    }
                    """)
                .variable("title", "Spring Security")
                .variable("category", "Java")
                .execute()
                .path("addBook.title")
                .entity(String.class)
                .isEqualTo("Spring Security");
    }

    @Test
    void missingBookIsNull() {
        graphQlTester
                .document("{ bookById(id: 9999) { title } }")
                .execute()
                .path("bookById")
                .valueIsNull();
    }
}
```

**Why `@Import(CatalogStore.class)`?** `@GraphQlTest` typically scans GraphQL controllers and related configuration components, not arbitrary `@Service` beans like a full `@SpringBootTest`. Importing the in-memory service gives the controller constructor its dependency. In production, you can mock the service and assert the resolver invokes the expected methods.

**Why doesn't this test verify the WebSocket handshake?** `@GraphQlTest` exercises the GraphQL execution layer without a live transport. It verifies schema/resolvers/arguments/GraphQL errors at the right level; WebSocket subprotocols, TLS/proxy, `Origin`, `connection_init`, auth, and reconnects require separate integration tests.

Run:

```bash
./gradlew test
```

Logically, passing means all three JUnit tests succeed; do not assume exact Gradle stdout formatting, which varies by version and console settings.

### 12.1. HTTP Integration Tests

With `@SpringBootTest(webEnvironment = RANDOM_PORT)`, Spring Boot can auto-configure `HttpGraphQlTester` against the live server depending on test dependencies. An end-to-end HTTP test should verify:

- `POST /graphql` with queries and variables.
- JSON response `data/errors` and media type.
- Authorization headers/cookies/CSRF policy matching deployment.
- Request body limits, parser errors, and invalid operations.
- Query complexity/rate limits.
- That a mutation modifies only authorized data and does not leak unauthorized records.

`GraphQlTester` is the general abstraction; `HttpGraphQlTester` and `WebSocketGraphQlTester` add transport specifics. Never treat a `@GraphQlTest` resolver unit test as proof that CDN/NGINX WebSocket routing works.

### 12.2. WebSocket Integration Tests

`WebSocketGraphQlTester` connects to the GraphQL WS transport over a shared WebSocket connection, allowing tests of `Flux` subscription results and cancellation. It requires a WebSocket client implementation and a real booted server. When designing the test:

1. Build the WebSocket tester targeting `ws://localhost:<port>/graphql/ws` using the live port.
2. Start `subscription { bookAdded { id title } }` first.
3. Wait until the subscription is active or use a synchronization hook in the test.
4. Send an HTTP mutation.
5. Assert the expected `bookAdded` event, cancel the subscription, and close the tester.
6. Test permission failures when credentials or `Origin` are missing.
7. Test reconnect/disconnect and cleanup; avoid multi-second fixed sleeps that make tests flaky.

In production, also test through the reverse proxy; a localhost WebSocket test can pass even when ingress fails to forward `Upgrade`.

## 13. Security: One GraphQL URL Does Not Mean One Permission Level

REST can authorize `/orders/**` by URL path. GraphQL funnels many operations and fields through `/graphql`, so **URL authorization is only the outer gate**:

```text
POST /graphql
    |
    +-- Query.books                 public or user
    +-- Query.bookById             tenant/permission check
    +-- Mutation.addBook           role EDITOR/ADMIN
    +-- Subscription.bookAdded     role SUBSCRIBER and scope filter
```

If security config only specifies `/graphql authenticated()`, any logged-in user might still lack permission for certain mutations or queries. You must authorize **fields, resolvers, services, and individual records**.

### 13.1. Spring Security for HTTP GraphQL

In a Servlet app with Spring Security, you can require authentication for HTTP GraphQL:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.POST, "/graphql").authenticated()
    .requestMatchers("/graphql/ws").authenticated()
    .anyRequest().denyAll()
);
```

This is a **policy snippet**, not a complete `SecurityFilterChain`. It assumes matching URLs and locks down other paths; apps serving public/static pages need matching rules ahead of the fallback. On the WebSocket path, handshake filters can require sessions/cookies or authentication, yet **after upgrade** you must still authorize each GraphQL operation rather than trusting an open socket blindly.

### 13.2. Authorization in Resolvers/Services

Spring Security method security can use `@EnableMethodSecurity` and `@PreAuthorize`:

```java
@MutationMapping
@PreAuthorize("hasRole('EDITOR')")
public Book addBook(
        @Argument("title") String title,
        @Argument("category") String category) {
    return store.add(title, category);
}
```

This is a **replacement snippet** for the demo method when Spring Security is present and configured. It does not run standalone. In production, also enforce authorization in the service/data layer so users cannot read or write another tenant's records even when guessing IDs. Subscriptions can outlive token/role lifetimes; establish a policy to revalidate or close them when permissions change.

### 13.3. WebSocket Authentication Differs from HTTP

Browser `new WebSocket()` does not let JavaScript attach arbitrary HTTP `Authorization` headers the way `fetch` does. Typical options include:

- Same-origin session cookies with TLS and proper CSRF/`Origin` protections.
- Tokens passed in `connection_init.payload` and validated via Spring GraphQL's `WebSocketGraphQlInterceptor`/`AuthenticationWebSocketInterceptor` when integrated with security.
- Credentials via subprotocol or query string **only with a carefully secured design**, avoiding leaking tokens in URL logs, referrers, and proxy analytics.

Spring for GraphQL 1.3 provides built-in support for authenticating during `connection_init` via Servlet/WebFlux interceptors. Simply sending `{"Authorization":"Bearer ..."}` in the payload **does not automatically turn it** into an authenticated `Principal` unless the proper interceptor is registered.

Avoid two vulnerabilities:
1. A socket that completed handshake with a role stays trusted forever even after the role or token is revoked.
2. A subscription opens against another topic/tenant simply by tampering with `variables`.

### 13.4. CORS Differs from WebSocket Origin

Boot's `spring.graphql.cors.*` configures CORS for HTTP GraphQL browser requests. Example for a cross-origin frontend:

```properties
spring.graphql.cors.allowed-origins=https://ui.example.test
spring.graphql.cors.allowed-methods=POST
spring.graphql.cors.max-age=1800s
```

This is an **example for truly cross-origin setups**, unnecessary for the same-origin browser demo. With cookie credentials, also align server CORS allow-credentials, `SameSite`/`Secure` cookies, and CSRF; never combine wildcard `Origin` with credentials.

WebSocket handshakes rely on `Origin`, which is not protected by HTTP CORS rules alone. Browser WebSockets can initiate cross-site connections; if auth cookies are sent automatically without `Origin` validation, you risk **Cross-Site WebSocket Hijacking**. Enforce an `Origin` allowlist, authentication, per-operation permissions, and network policies. Non-browser clients can spoof `Origin`, so `Origin` never replaces authentication.

### 13.5. CSRF with Cookies/Sessions and HTTP Mutations

If Spring Security uses session/cookie authentication, GraphQL POST mutations can be rejected by CSRF protection when the CSRF token is missing. Queries also typically use POST at `/graphql`, so you cannot simply treat "GET is safe, POST mutates state" and disable CSRF across all POSTs. Depending on the app:

- Integrate browser cookie-authenticated GraphQL POST requests with proper CSRF token flows.
- For stateless bearer-token APIs not using cookies, design the security chain and CSRF policy around your threat model.
- Consider separating endpoints/methods/authorization or using persisted queries when appropriate.
- Never call `csrf.disable()` app-wide just to "make GraphQL POST work."

The demo omits the security starter to focus on transports; **never deploy it to the public Internet without adding protections**.

## 14. Depth Limits, Complexity Limits, and N+1

GraphQL is flexible for clients, yet unbounded queries can trigger massive load:

```graphql
query {
  teams {
    members {
      projects {
        tasks {
          comments {
            author {
              name
            }
          }
        }
      }
    }
  }
}
```

Even if every individual field is cheap, nested list fan-outs multiply DB queries, CPU, and memory. Enforce limits:

- **Max query depth**: reject overly deep nesting.
- **Max query complexity/cost**: estimate execution cost from fields, list sizes, and arguments.
- **Pagination**: require `first/after` or bounded offset/limit.
- **Rate limiting/quotas**: per user/tenant/token, including active connections/subscriptions.
- **Request body/document size**: block oversized GraphQL documents.
- **Execution timeout/cancellation**: abort slow downstream queries rather than pinning threads indefinitely.
- **Persisted queries/allowlists** for first-party clients where appropriate.
- **Introspection policy** per environment. Disabling introspection does not replace authentication.

GraphQL Java provides instrumentations like `MaxQueryDepthInstrumentation` and `MaxQueryComplexityInstrumentation`; Spring Boot offers the `GraphQlSourceBuilderCustomizer` hook to customize the GraphQL runtime. Benchmark and tune against your real schema instead of picking arbitrary numbers. A shallow query with loose pagination can still exhaust resources.

### 14.1. N+1 Queries When Resolvers Load Relations

For `books { author { name } }`, an `author` resolver might query the database once per book, resulting in 1 + N queries. Spring for GraphQL supports `DataLoader`/`@BatchMapping`:

```java
@BatchMapping
public Map<Book, Author> author(List<Book> books) {
    // Query all related authors in one batch,
    // returning Map<Book, Author> so GraphQL maps each to its parent.
    return authorService.loadAuthorsFor(books);
}
```

This is a **snippet** assuming `Author`/`authorService` and `Book.author` in the schema. It is not part of the runnable app in Section 7. With JPA, account for N+1 in ORM fetch plans and tenant authorization as well; `DataLoader` batches calls but does not automatically fix every slow query.

### 14.2. Can Only Fields Present in the Schema Be Queried?

The GraphQL schema acts as an API-layer field allowlist. However, a field existing in the schema **does not mean every user is allowed to read it**. If `User.email` or `Admin.auditLog` is in the schema, services must authorize by role/owner/tenant. Introspection makes schemas easy to discover, yet attackers can still guess field names; **disabling introspection does not replace authorization**.

## 15. Error Handling and Observability

Spring for GraphQL provides `DataFetcherExceptionResolver` to translate DataFetcher exceptions into safe GraphQL errors with appropriate `extensions.classification` or error codes. For instance, a permission-denied mutation should emit a structured client-readable error without exposing stack traces or SQL messages.

Do not throw arbitrary Java exceptions expecting HTTP 500 like REST every time: GraphQL execution can place errors inside `errors` alongside partial data. Establish a clear contract:

- Concise user-facing messages revealing no internals.
- Stable error codes for clients where needed.
- Correlation/request IDs linking logs and traces.
- Classification of retryable vs. non-retryable errors.
- Proper transaction rollback on failures.
- Field-level authorization that avoids leaking existence/names of other tenants' resources unnecessarily.

### 15.1. Observability

Monitor:

- `graphql.operation`/operation name (watch label cardinality) and query/mutation/subscription type.
- Execution time p50/p95/p99 and GraphQL error counts.
- Field resolver latency, DB queries per request, and N+1 patterns.
- Active WebSocket connections, active subscriptions, and `connection_init` failures.
- Protocol close codes, reconnect rates, and client disconnects/cancellations.
- CPU, heap, connection buffers, and Reactor sink dropped events.
- Broker lag, queue depth, and replay gaps if using a durable event source.
- HTTP 401/403s, subscription authorization denials, and CORS/`Origin` failures.
- **Both** HTTP status and GraphQL `errors`; tracking only HTTP 200 masks field errors.

Never log raw GraphQL variables containing passwords, tokens, or PII, and never attach user IDs or full operation documents as metric labels. Avoid exposing stack traces in production or leaving GraphiQL/schema printer open uncontrolled.

## 16. NGINX and Ingress: HTTP + WebSocket on the Same App

A reverse proxy can let public clients POST `/graphql` and open WebSocket `/graphql/ws`. For HTTP/1.1 WebSocket, the proxy must forward `Upgrade`/`Connection` headers; a plain HTTP GET to `/graphql/ws` is insufficient.

NGINX test-environment snippet; `map` belongs in the `http` block, and `server` also sits under `http`:

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 8081;
    server_name localhost;

    location = /graphql/ws {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 90s;
        proxy_send_timeout 90s;
    }

    location = /graphql {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;

        # If using GraphQL SSE, test buffering carefully.
        proxy_buffering off;
        proxy_read_timeout 90s;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
    }
}
```

This is an **illustrative server block**, not a complete production NGINX config. When NGINX runs in another container, `127.0.0.1:8080` refers to the NGINX container itself; replace the upstream with the appropriate service DNS. For public HTTPS, configure TLS, pass `Host`/forwarded headers safely, and use `wss://` in the browser. Do not expose this plain HTTP snippet as a public production endpoint.

**Proxy/WebSocket notes:**

- `Upgrade` and `Connection` are hop-by-hop HTTP/1.1 headers; proxies must forward them during handshake.
- `proxy_read_timeout` bounds idle periods with no upstream data; it does not keep a WebSocket alive for 90s regardless of traffic.
- GraphQL WS keep-alive pings and WebSocket control ping/pong frames operate at different layers; test compatibility across every proxy hop.
- When using a CDN/load balancer, confirm WebSocket support and idle timeouts; not all CDN cache rules apply to WS.
- With HTTP/2 or HTTP/3 between browser and edge, WebSocket may use extended CONNECT depending on the stack; do not assume every hop behaves like HTTP/1.1 Upgrade.
- GraphQL SSE streams over HTTP; proxy buffering or compression can delay or batch events before reaching the client.
- Never shared-cache GraphQL responses containing personalized data. POST is usually uncached by default, though CDNs/custom gateways can be configured otherwise; enforce cache policies per user/tenant.

## 17. Subscriptions Across Multiple Replicas: Enabling WebSocket Alone Is Not Enough

Consider 2 Spring Boot instances, A and B:

```text
              Browser 1              Browser 2
                 |                       |
            WS subscribed           WS subscribed
                 |                       |
               Pod A                   Pod B
                 \                       /
                  \                     /
                   Shared Event Broker
                  /                     \
           Business producer        Business producer
```

In the demo, `CatalogStore` creates a **`Sinks.Many` per JVM**. A mutation hitting Pod A emits events only to subscribers connected to Pod A. A browser connected via WebSocket to Pod B will **not** receive events produced on A. The same problem happens during app restarts, autoscaling, and rolling deploys.

To scale horizontally:

1. Commit business changes in the database inside a proper transaction.
2. Publish events through a shared bus/broker; for durability use an outbox/event log.
3. Each pod consumes events and pushes them to GraphQL subscription clients connected to that pod.
4. Check user/tenant/room filters before emitting.
5. Define ordering, at-least-once vs. best-effort semantics, idempotency, dedup, and replay.
6. Cap subscriber/queue counts and define slow-client behavior.
7. When a WebSocket reconnects to another pod, the client sends a cursor or fetches a snapshot before resubscribing.

Sticky sessions only keep a client on one pod while that pod lives; **they do not replicate in-memory state or save sockets across pod restarts**.

### 17.1. GraphQL Subscriptions Are Not Automatic Database Change Feeds

Merely adding `@SubscriptionMapping` does not make Spring Data/JPA emit events when a table changes. You must wire an event source into `Flux`/`Publisher`. With Redis Pub/Sub, disconnected subscribers miss events; with Kafka/Redis Streams, configure cursors, retention, and consumer offsets properly. Choose based on product requirements rather than simply wanting "GraphQL WS."

### 17.2. Slow Subscribers and Backpressure

GraphQL WebSocket can multiplex many operations, yet browsers do not always consume fast enough. If events arrive at 1,000/s while a client renders 10/s, buffers can grow. In Spring MVC, writes may block on an async executor; WebFlux uses non-blocking I/O and Reactor backpressure in the pipeline, though network buffers, queues, and browser limits still matter.

With `directBestEffort` in the demo, slow subscribers drop events instead of buffering unboundedly. When every event is required, use a durable queue/cursor with replay rather than switching to an unbounded `onBackpressureBuffer()`, which risks OOM.

## 18. WebFlux and RSocket: Same Schema, Different Transport Runtime

Spring Boot supports several options:

| Stack | Dependencies | HTTP GraphQL | GraphQL WS |
| --- | --- | --- | --- |
| Servlet MVC | graphql + web + websocket | Yes | Yes, once websocket path is configured |
| WebFlux | graphql + webflux | Yes | Yes, once websocket path is configured |
| RSocket | graphql + rsocket | Over RSocket request-response/stream | Distinct from HTTP GraphQlWebSocketHandler |

If an application uses **only** WebFlux, you do not need Servlet `spring-boot-starter-websocket`; Spring GraphQL includes a WebFlux WS handler. Still, reactive `GraphQlWebSocketHandler` is not raw Spring MVC `TextWebSocketHandler`. Similarly, GraphQL-over-RSocket is a separate transport from GraphQL-over-WebSocket using `graphql-transport-ws`.

Do not mix `spring-boot-starter-web` and `spring-boot-starter-webflux` assuming the app automatically becomes reactive: Boot follows application-type precedence rules; pick your stack explicitly.

### 18.1. Blocking vs. Non-Blocking Resolvers

A `@QueryMapping` returning `List<Book>`/making a JPA call can block its thread; `@SubscriptionMapping` returns `Flux<Book>` for multi-item streams. A WebFlux event loop must not run blocking JDBC/I/O directly; offload to a suitable executor/scheduler or use genuinely reactive persistence.

Spring GraphQL 1.3 allows configuring an executor for blocking controller methods, including virtual threads on Java 21+ with the corresponding Spring Boot property. This lesson's example uses **Java 17** and in-memory operations, so virtual threads are not required.

### 18.2. Reactive Streams Do Not Replace Business Replay

GraphQL subscriptions use Reactive Streams `Publisher`/`Flux` to emit multiple results, yet if a client disconnects, data is not automatically persisted. Backpressure governs emission/consumption rate; replay/durability is a separate storage and business semantics concern. Never assume `Flux` alone guarantees "zero lost events."

## 19. Common Errors and How to Diagnose Them

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| POST `/graphql` 404 | Missing web starter/changed path or app failed to start | Check Boot dependencies and `spring.graphql.path` |
| App startup fails with schema error | Invalid SDL, missing `graphql/*.graphqls`, or mapping mismatch | Check SDL syntax and schema inspection |
| HTTP query returns `errors` | Invalid field/argument, resolver error, missing auth | Check HTTP status, `data`, and `errors` together |
| Field returns null | No record found or resolver error/permission denial | Check field nullability and `errors` |
| `bookAdded` emits no events | Not subscribed yet, mutation fired too early, best-effort sink | Subscribe first, instrument sink emissions and source |
| WS handshake 404 | WebSocket starter missing or path not configured | Enable `spring.graphql.websocket.path` + starter |
| WS handshake 400/403 | Wrong subprotocol, `Origin`, or handshake security | Use `graphql-transport-ws` and aligned policies |
| WS opens then closes | `connection_init` missing, timeout, or proxy idle limit | Check connection-init protocol, keepalive, logs |
| WS gets ACK but no `next` | `subscribe` not sent, wrong operation/query, no source events | Inspect WS frames and resolver/sink |
| Client sends legacy `graphql-ws` subprotocol | Confused with `subscriptions-transport-ws` | Switch to `graphql-transport-ws` from modern `graphql-ws` |
| SSE POST fails with `EventSource` | Native `EventSource` sends GET without body | Use fetch-stream or a GraphQL SSE client |
| Client checks only HTTP 200 | GraphQL errors live inside JSON response | Inspect `errors`/partial data |
| Queries slow down sharply with nested relations | N+1 and deep nesting | `@BatchMapping`/DataLoader, depth/cost/pagination |
| High CPU from subscriptions | Too many active connections, heavy resolvers, slow consumers | Connection limits, throttling, fan-out architecture |
| One pod sees events, another does not | Local in-memory sink without shared broker | Pub/Sub/outbox/broker and subscription routing |
| Mutation succeeds yet client misses event | Event loss/race or listener on another pod | Durable replay where needed, multi-replica tests |
| GraphiQL publicly accessible | Dev property left enabled in production | Disable/secure GraphiQL and introspection per policy |
| POST mutation returns 403 under Spring Security | Missing CSRF token or role/policy | Define proper auth/CSRF flow; never disable blindly |
| WebSocket uses `ws://` on an HTTPS page | Mixed content / TLS termination | Use `wss://` and configure HTTPS proxy properly |
| Reconnect causes duplicate data | At-least-once replay without dedup | Event IDs, unique constraints/idempotency |
| WS request through NGINX returns 400 | Proxy fails to forward `Upgrade`/`Connection` | Configure WebSocket hop headers properly |
| Personalized response gets cached | Misconfigured CDN/gateway cache policy | Private/no-store/authorization and cache keys |

## 20. Self-Check Exercises

**1.** You have `type Query { books: [Book!]! }` and `@QueryMapping books()`. Do you need to write `@PostMapping("/graphql")`?  
**Answer:** No. Spring Boot/Spring for GraphQL creates the GraphQL HTTP handler automatically; resolver methods only bind to schema fields.

**2.** A project only includes `spring-boot-starter-graphql` and `spring-boot-starter-web`. Is WebSocket GraphQL working yet?  
**Answer:** Not yet. On Servlet you need the WebSocket starter and `spring.graphql.websocket.path`. HTTP POST can work while WS is not exposed.

**3.** A browser opens WS with subprotocol `graphql-ws` from the legacy library and sends `GQL_START`, while Spring GraphQL expects `graphql-transport-ws`. What happens?  
**Answer:** Protocol incompatibility. Use the modern `graphql-ws` client with subprotocol `graphql-transport-ws` and `connection_init/subscribe/next` messages.

**4.** Mutation `addBook` returns HTTP 200 yet the response contains `errors`. Can you consider it completely successful?  
**Answer:** No. Clients must check `errors` and `data` per GraphQL response semantics; HTTP status alone is insufficient.

**5.** Does GraphQL `String!` block empty strings `""`?  
**Answer:** No, non-null does not mean non-blank. Enforce business validation such as `isBlank()` checks in the service.

**6.** A subscription client received `connection_ack` yet sees no new events. What should you check?  
**Answer:** Verify `subscribe` was sent with valid `id/payload/query`, the subscription became active, the mutation emitted an event, the sink had subscribers without overflow, and check proxies/permissions/multi-pod routing.

**7.** After a JVM restart, does a browser WebSocket reconnect automatically and receive missed events?  
**Answer:** No. Browser WebSockets do not auto-reconnect and GraphQL protocol does not auto-replay; implement client reconnect + durable event cursor/replay if required.

**8.** Does a passing `GraphQlTester` test under `@GraphQlTest` prove WS through NGINX works?  
**Answer:** No. It tests GraphQL execution without starting transports; you need live WebSocket integration tests and proxy verification.

**9.** A GraphQL query has depth 8, where each list holds thousands of elements. Can it overload the server despite shallow depth?  
**Answer:** Yes. Enforce complexity/cost limits, pagination, quotas, DataLoader, and timeouts — not just max depth.

**10.** An authenticated user runs a GraphQL query requesting another user's email field. Is `/graphql authenticated()` enough?  
**Answer:** No. Enforce authorization in resolvers/services and at the object level.

**11.** Can native `EventSource("/graphql")` send the GraphQL subscription POST JSON body used for Spring GraphQL SSE in this lesson?  
**Answer:** No. Native `EventSource` sends GET; use a GraphQL SSE client or `fetch` streaming POST.

**12.** Across 3 pods, why shouldn't you rely on a local `Sinks.Many` to ensure all subscribers receive mutations?  
**Answer:** A local sink lives inside one JVM and is not shared across pods. Use a shared event bus and, for durability, an event store/outbox/replay mechanism.

## 21. Production Checklist

- [ ] GraphQL SDL schema is version-controlled, reviewed, and tested against breaking changes.
- [ ] Query/Mutation and Subscription have distinct limits rather than treating all GraphQL operations identically.
- [ ] Spring Boot starters match the chosen stack; WS path is enabled deliberately, not assumed present.
- [ ] Client and server agree on **`graphql-transport-ws`**; no legacy protocol confusion.
- [ ] GraphQL HTTP clients send JSON `query/variables/operationName` and handle both `data` and `errors`.
- [ ] WebSocket clients send `connection_init`, await ACK before `subscribe`, and cancel/close when unused.
- [ ] Subscription sources actually emit events; event reliability (best-effort vs. durable) is explicitly defined.
- [ ] AuthN/AuthZ are enforced at HTTP, WS handshake, operations, and object/tenant fields.
- [ ] Browser CORS/`Origin`, cookies/CSRF, and TLS/WSS policies are configured properly.
- [ ] Query depth, cost/complexity, pagination, request size, rate limits, and execution timeouts are configured.
- [ ] Resolver N+1 queries are measured and mitigated with batching/DataLoader where needed.
- [ ] Introspection, GraphiQL, schema printer, and sensitive logging are restricted in production.
- [ ] WS keepalive, proxy `Upgrade`/idle timeouts, SSE buffering, and reconnects are tested across real edge infrastructure.
- [ ] Metrics track WS connection/subscription counts, queue sizes, dropped events, and error rates.
- [ ] Multi-replica deployments use a shared broker rather than local in-memory sinks or sticky sessions for event delivery.
- [ ] Tests cover GraphQL schema/resolvers, HTTP status/errors, WS handshakes, and live network subscriptions.
- [ ] Reconnect/backoff/resubscribe/cursor/replay plans exist for client or node disconnects.
- [ ] State-changing mutations use transactions/idempotency where required and align event emission with commits.
- [ ] Rollouts include rollback plans, log redaction, and controlled diagnostic access.

## Official References

1. [Spring Boot 3.3 — Spring for GraphQL](https://docs.spring.io/spring-boot/3.3/reference/web/spring-graphql.html)
2. [Spring Boot 3.3 — Application Properties: spring.graphql.*](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
3. [Spring Boot 3.3 — Testing Spring GraphQL](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
4. [Spring for GraphQL — Annotated Controllers, @QueryMapping, @MutationMapping, @SubscriptionMapping](https://docs.spring.io/spring-graphql/reference/controllers.html)
5. [Spring for GraphQL — HTTP, WebSocket, and SSE Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
6. [Spring for GraphQL — GraphQlTester Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
7. [graphql-ws — GraphQL over WebSocket Protocol](https://github.com/enisdenjo/graphql-ws/blob/master/PROTOCOL.md)
8. [GraphQL over HTTP Working Draft](https://graphql.github.io/graphql-over-http/draft/)
9. [GraphQL Specification](https://spec.graphql.org/)
10. [Project Reactor — Sinks.MulticastSpec directBestEffort](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.MulticastSpec.html)
11. [NGINX — WebSocket Proxying](https://nginx.org/en/docs/http/websocket.html)
12. [Spring Security — Method Security and Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)

**Key takeaway:** GraphQL defines **schemas and operations**; HTTP POST and WebSocket are **transports** carrying those same operations into Spring for GraphQL. Queries/mutations typically use HTTP, while subscriptions typically use WebSocket with `graphql-transport-ws` (or SSE when clients/infrastructure fit). Choosing the right transport is only the first step; **field-level authorization, query cost limits, connection lifecycles, replay, and multi-node scaling** determine whether a GraphQL API runs safely and reliably.