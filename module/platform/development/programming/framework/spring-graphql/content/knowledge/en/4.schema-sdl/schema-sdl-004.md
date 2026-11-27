# `type Subscription`

## 1. What is a Subscription in GraphQL?

GraphQL defines three schema-level operation types: `Query` for reading data, `Mutation` for modifying data, and `Subscription` for receiving updates as events occur. Specifically, `Subscription` describes the event streams that clients can subscribe to.

A regular query produces a single result for a single execution. A subscription produces a stream of results: whenever the event source emits a new event, the server executes the subscription's selection set and sends a corresponding response to the client. As a result, clients can receive changes without repeatedly polling the server with queries.

In Schema Definition Language (SDL), the root type for subscriptions is typically declared as:

```graphql
type Subscription {
    bookChanged: Book
}
```

`Subscription` is an object type. The `bookChanged` field is an event-subscription capability published in the schema. The SDL declaration only describes the field name, arguments, and return data type; it does not create the event source, decide how subscribers are authenticated, or establish the network connection.

In Spring for GraphQL, this field is typically mapped to a `@SubscriptionMapping` method returning a publisher, such as `Flux<T>`. The subscription execution engine and transport layer are responsible for maintaining the stream of responses to the client.

## 2. Declaring the root Subscription type in the schema

### Root type naming conventions

By GraphQL's default convention, root operation types are named `Query`, `Mutation`, and `Subscription`. If a schema does not explicitly declare a `schema` block, GraphQL uses these default names when they exist and match their corresponding operations.

A schema can declare its root types explicitly:

```graphql
schema {
    query: Query
    mutation: Mutation
    subscription: Subscription
}

type Query {
    book(id: ID!): Book
}

type Mutation {
    updateBookTitle(id: ID!, title: String!): Book!
}

type Subscription {
    bookChanged: BookChangeEvent!
}

type Book {
    id: ID!
    title: String!
}

type BookChangeEvent {
    bookId: ID!
    title: String!
}
```

In the example above, `query`, `mutation`, and `subscription` in the `schema` block are operation root names; `Query`, `Mutation`, and `Subscription` are the object type names used as roots. A query root is mandatory for an executable GraphQL schema. Mutation and subscription are optional if the API does not provide those two operation types.

If you want to use a different object type name, you must declare the mapping explicitly:

```graphql
schema {
    query: Query
    subscription: LiveUpdates
}

type Query {
    health: String!
}

type LiveUpdates {
    systemNotice: String!
}
```

Here `LiveUpdates` is the subscription root type. Without a custom `schema` declaration, do not rename `Subscription` and expect GraphQL to recognize the new type automatically.

### What is a field in Subscription?

Each field of the root `Subscription` type represents an event stream clients can subscribe to. A field can accept arguments to filter or scope the subscription, and can return a scalar, enum, object, or other valid output type.

Example:

```graphql
type Subscription {
    systemNotice: String!
    bookChanged(bookId: ID!): BookChangeEvent!
    orderStatusChanged(orderId: ID!): OrderStatusEvent!
}
```

- `systemNotice` provides system notifications.
- `bookChanged` allows tracking changes to a specific book.
- `orderStatusChanged` allows tracking the status of an order.

An object type must have at least one field. Therefore, once `type Subscription` is declared, at least one meaningful field must be defined. If the application does not yet need event streaming, you can omit the subscription root type.

## 3. Designing data types for events

A subscription can return a domain object directly, such as `Book!`. However, when clients need to know the kind of change, when it occurred, or an event identifier, you should design an object type representing an event payload.

Example:

```graphql
enum BookChangeKind {
    CREATED
    UPDATED
    DELETED
}

type BookChangeEvent {
    eventId: ID!
    bookId: ID!
    kind: BookChangeKind!
    occurredAt: String!
    book: Book
}

type Book {
    id: ID!
    title: String!
    authorName: String!
}

type Subscription {
    bookChanged(bookId: ID!): BookChangeEvent!
}
```

The `BookChangeEvent` payload carries common event metadata. The `book` field can be `null`, for example when a book has been deleted and the server no longer has a current object to return. Meanwhile, `eventId`, `bookId`, `kind`, and `occurredAt` are declared non-null because the example assumes every valid event carries those fields.

In the example, `occurredAt` uses `String` with an ISO-8601 timestamp convention. If you want the schema to express the timestamp type more explicitly, you can define a custom scalar such as `DateTime`, though the server must register the corresponding scalar and specify its serialization/parsing format. Merely declaring `scalar DateTime` in SDL does not automatically generate a Java converter.

### Why use a dedicated event payload?

A dedicated payload lets the API express the semantics of an event rather than sending a raw data record without context. It also allows the schema to evolve as needed without modifying the core entity type.

An event payload commonly includes:

- `eventId`: event identifier, useful for logging, reconciliation, or deduplication.
- `kind`: change type such as `CREATED`, `UPDATED`, or `DELETED`.
- `occurredAt`: timestamp when the event occurred following a consistent convention.
- `entityId`: identifier of the affected domain entity.
- `entity`: current data or a snapshot at event time, if business rules allow.
- `changedFields`: a list or structure describing which properties changed, if clients genuinely need it.

Do not include the entire entity or internal data in the payload by default. Expose only the fields clients need and are authorized to view. The more stable the payload, the less server-side storage model changes will affect subscribed clients.

## 4. Using arguments to scope the event stream

If every client receives every event, the server may transmit large volumes of data and authorization becomes hard to enforce. Arguments allow clients to subscribe to a specific scope.

Simple example:

```graphql
type Subscription {
    bookChanged(bookId: ID!): BookChangeEvent!
}
```

A client subscribes to watch a single book:

```graphql
subscription WatchBook($bookId: ID!) {
    bookChanged(bookId: $bookId) {
        eventId
        kind
        occurredAt
        book {
            id
            title
        }
    }
}
```

Variables sent with the operation:

```json
{
  "bookId": "book-42"
}
```

Arguments in SDL use valid input types. If multiple filter conditions are needed, you can group them into an input object:

```graphql
input BookChangeFilter {
    bookId: ID
    authorId: ID
    kinds: [BookChangeKind!]
}

type Subscription {
    bookChanged(filter: BookChangeFilter!): BookChangeEvent!
}
```

`BookChangeFilter` is an input type, so it can only contain scalars, enums, input objects, and lists of appropriate input types. You cannot directly use an output object like `Book` as an argument type. In real-world design, consider whether filters should be required and how the server handles missing or empty filters.

Arguments only describe the subscription criteria. The server must still apply filtering at the event source or in the processing layer before emitting events to subscribers. Filtering only on the client after sending every event over the network does not reduce server load and can leak data.

## 5. Key rule of Subscription operations

A subscription operation has one rule that differs from regular queries: its top-level selection set must select exactly one root field. This is required so the server can identify a single event source per subscription operation.

Valid example:

```graphql
subscription WatchBook {
    bookChanged(bookId: "book-42") {
        eventId
        kind
    }
}
```

Invalid example because it has two root fields:

```graphql
subscription WatchEverything {
    bookChanged(bookId: "book-42") {
        eventId
    }
    systemNotice
}
```

If a client needs to monitor two independent event types, create two separate subscription operations. The same WebSocket connection can manage multiple active operations, depending on the transport protocol and server limits.

Nested fields inside the payload can still be freely selected according to the schema:

```graphql
subscription WatchBook {
    bookChanged(bookId: "book-42") {
        eventId
        kind
        book {
            id
            title
            authorName
        }
    }
}
```

Thus, the single-field rule applies only to the root selection set of the subscription operation; it does not limit the number of fields inside the payload object.

## 6. Nullability and lists in event payloads

Nullable (`T`) and non-null (`T!`) rules in SDL remain in effect for each response emitted by a subscription.

```graphql
type Subscription {
    bookChanged(bookId: ID!): BookChangeEvent!
}

type BookChangeEvent {
    eventId: ID!
    book: Book
    tags: [String!]!
}
```

Meaning of the types in the example:

| Declaration | Meaning |
| --- | --- |
| `BookChangeEvent!` | Each event payload cannot be `null` |
| `Book` | The book object may be `null` |
| `[String!]!` | The list always has a value and no element in the list may be `null` |
| `[String]` | The list may be `null`, and individual elements may also be `null` |

If a non-null field cannot be resolved, the error can bubble up to the nearest nullable parent field. For subscriptions, this happens in the response for that specific event; design nullability around the real data of each event kind. For example, a book deletion event may no longer have a `book`, so declaring `book: Book` is more appropriate than `book: Book!` if the payload still needs to be emitted.

## 7. Schema descriptions and evolving Subscription fields

You can use descriptions in SDL to document the meaning of the root type and fields:

```graphql
"""Event streams related to the library."""
type Subscription {
    """Emits an event when a book changes."""
    bookChanged(bookId: ID!): BookChangeEvent!
}
```

Descriptions help documentation generators and schema consumers understand event scope. Descriptions should clarify who can subscribe, filter conditions, payload semantics, and important business constraints.

When replacing a subscription field, you can mark the old field with `@deprecated`:

```graphql
type Subscription {
    bookChanged(bookId: ID!): BookChangeEvent!
        @deprecated(reason: "Use catalogBookChanged instead")

    catalogBookChanged(bookId: ID!): BookChangeEvent!
}
```

Keeping the old field during a transition period gives clients time to migrate. Before removing the field, monitor usage and coordinate the release schedule with active clients.

## 8. From SDL to Spring for GraphQL

SDL defines the contract. Spring for GraphQL needs a resolver to supply an event publisher matching the declared field.

With the schema:

```graphql
type Subscription {
    bookChanged(bookId: ID!): BookChangeEvent!
}
```

A controller can map this field using `@SubscriptionMapping`:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class BookSubscriptionController {

    private final BookEventService bookEventService;

    public BookSubscriptionController(BookEventService bookEventService) {
        this.bookEventService = bookEventService;
    }

    @SubscriptionMapping
    public Flux<BookChangeEvent> bookChanged(@Argument String bookId) {
        return bookEventService.subscribeToBook(bookId);
    }
}
```

`@SubscriptionMapping` binds the method to the identically named field on the root `Subscription` type. `@Argument` receives the `bookId` value from the operation. `BookEventService` is responsible for creating a publisher emitting matching events; this example assumes the service returns `Flux<BookChangeEvent>`.

An alternative is `@SchemaMapping(typeName = "Subscription", field = "bookChanged")`, though `@SubscriptionMapping` expresses subscription handling intent more clearly and is usually easier to read.

Key distinctions:

- SDL describes the fields and data types clients are allowed to request.
- `@SubscriptionMapping` maps a schema field to a Java method.
- A `Flux` or `Publisher` provides the stream of values over time.
- An event broker, message queue, or domain service produces and distributes events.
- The transport delivers subscription responses to the client.

If SDL declares `bookChanged` without a matching resolver or data source, the schema can still be parsed, but the subscription will not work as expected. Conversely, a Java method does not automatically become a public API without a corresponding schema field and configured mapping.

## 9. Transport and subscription lifecycle

GraphQL SDL does not mandate whether subscriptions use WebSocket, Server-Sent Events, or another specific transport mechanism. GraphQL execution produces a stream of results; the application needs a transport capable of delivering multiple responses over the lifetime of the subscription.

In the Spring for GraphQL ecosystem, WebSocket is a common choice for subscriptions. Some systems may use other streaming transports if both framework and client support them. Standard HTTP request-response returns a single response and completes, so having a `/graphql` endpoint via Spring MVC does not by itself mean subscriptions are working.

General lifecycle:

1. The client sends the subscription operation and arguments to the transport.
2. The server authenticates the user, checks subscription permissions, and creates the corresponding publisher.
3. The event source emits a new event.
4. GraphQL executes the selection set for that event and produces a response.
5. The transport sends the response to the client; this repeats until the operation is cancelled, errors out, or completes.

When a client disconnects or cancels an operation, the server must clean up the subscription and associated resources. With shared event sources, cancelling one client must not stop streams for other clients. Design cleanup, backpressure, and concurrent-subscription limits appropriate to system capacity.

## 10. Security and reliability of event streams

Subscriptions live longer than ordinary requests. Checking permissions at connection time is necessary but may be insufficient if access rights or business state change while a client is subscribed.

Design principles:

- Authenticate the user when establishing the operation or connection according to the transport's mechanism.
- Verify permission to view objects passed via arguments, such as `bookId` or `orderId`.
- Filter events server-side by tenant, owner, and permitted data scope.
- Re-evaluate permissions upon event emission if security policy requires permissions to remain valid throughout the subscription lifecycle.
- Limit subscription count, event rate, and payload size per user or tenant.
- Do not write tokens, personal information, or sensitive payloads to unprotected logs.

An interrupted streaming connection can cause clients to miss events. GraphQL subscriptions do not inherently guarantee event persistence, replay after reconnect, global ordering, or exactly-once processing. If business requirements demand resuming from a prior position, design event IDs or cursors and a replay mechanism at the event-source layer. Clients should also have a way to resynchronize current state via queries when needed.

## 11. Testing schemas and subscriptions

Test the SDL contract, resolvers, and transport separately, as each layer can fail differently.

**Schema testing:** verify the subscription root type is properly declared, fields have valid output types, arguments use input types, and referenced types exist. If the schema uses a custom root name, verify the `schema` block maps it properly.

**Mapping testing:** verify SDL fields map to `@SubscriptionMapping`, arguments are passed properly, and the publisher emits expected payloads. Test empty streams (no events), publisher completion, and publisher errors.

**Operation rule testing:** verify subscription operations have only a single root field. While queries with multiple root fields may be valid, subscriptions with multiple root fields must be rejected during validation.

**Authorization and lifecycle testing:** test unauthorized users, invalid filters, operation cancellation, disconnects, and multiple concurrent subscribers. Confirm cancelling one subscription does not affect others.

**Transport testing:** use the exact protocol deployed in production. A test calling the publisher directly does not prove the WebSocket or streaming endpoint is configured properly.

## 12. Common design mistakes

| Issue | Consequence | How to address |
| --- | --- | --- |
| Having `type Subscription` without declaring root in a custom schema | GraphQL does not recognize that type as the subscription root | Add `subscription: Subscription` in the `schema` block |
| Renaming the root type without declaring schema mapping | Root operation is not mapped by default name | Keep the name `Subscription` or declare the root type explicitly |
| Subscription operation has multiple root fields | Invalid operation | Split into separate subscription operations |
| Field lacks filters for broad event scopes | Server may broadcast unnecessary data to many clients | Design arguments and filter server-side |
| Payload returns only the entity without event context | Clients struggle to distinguish creation, update, and deletion | Use a dedicated event payload when business logic needs metadata |
| Declaring `book: Book!` when deletion events have no entity | Non-null propagation can wipe desired data from the response | Choose nullability per event kind or use an appropriate snapshot |
| Checking permissions only when opening the connection | Users may keep receiving events after permissions change | Re-evaluate permissions per the system's security policy |
| Assuming GraphQL automatically replays events after reconnect | Clients can miss updates | Add cursors, replay, and state resynchronization if needed |
| Configuring only HTTP request-response | Clients do not receive a stream of subscription responses | Configure a compatible streaming transport on server and client |

## 13. Checklist for designing `type Subscription`

- [ ] Schema has a subscription root type and explicit mapping if using a custom name.
- [ ] Each field represents a clearly defined event stream.
- [ ] Arguments use valid input types and support business-scoped filtering.
- [ ] Payloads contain necessary metadata without exposing excess data.
- [ ] Nullability fits every event kind, including object deletion.
- [ ] Client operations select exactly one root field.
- [ ] Spring for GraphQL has a resolver returning a publisher matching the SDL field.
- [ ] Streaming transport is configured and tested with real clients.
- [ ] Authentication, authorization, resource limits, and cancellation cleanup are in place.
- [ ] Reconnect, replay, or state-resynchronization strategy exists if required by business rules.

## Conclusion

`type Subscription` is the root object type describing event streams published by a GraphQL API to clients. Each field represents a subscription type, can accept arguments to define scope, and returns a structured payload. A key rule of subscription operations is having only one root field in the selection set.

In Spring for GraphQL, the SDL schema must be connected to a `@SubscriptionMapping` resolver returning a publisher, alongside a transport capable of streaming multiple responses. Good design accounts for payloads, nullability, server-side filtering, lifecycle authorization, cleanup, and recovery after disconnects. When these parts are designed cohesively, Subscriptions become a practical mechanism for building event-driven updates in a GraphQL API.
