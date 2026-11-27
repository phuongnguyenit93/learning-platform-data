# Limitations of GraphQL

## GraphQL fundamentals

GraphQL lets clients describe the exact data they need to receive in an operation. This approach helps reduce the over-fetching or under-fetching commonly encountered when a REST API must serve multiple screens and multiple client types. A strongly typed schema also helps clients discover the API and catch certain errors during development.

However, GraphQL does not automatically make a system faster, safer, or easier to operate. It shifts part of the decision over query structure to the client while placing added responsibilities on the server: controlling query cost, coordinating data loading, protecting individual fields, and observing API behavior. Understanding these limitations helps you choose GraphQL in the right places and design Spring for GraphQL with control.

## 1. GraphQL does not guarantee better performance

GraphQL is a query language and an API execution mechanism. It does not determine how the database is queried, does not create indexes on its own, and does not guarantee that one operation translates to a single SQL statement.

For example, a client sends a request to fetch a list of books along with their authors:

```graphql
query BookList {
  books(first: 20) {
    title
    author {
      name
    }
  }
}
```

The server may handle `books` with one query, then call the `author` resolver separately for each book. In that case, a single GraphQL request can trigger many database accesses or multiple calls to downstream services. Fewer HTTP requests do not automatically mean fewer backend operations.

Performance depends on resolver implementation, data modeling, querying strategy, caching, and resource limits. Measure execution time and backend access counts rather than evaluating performance solely by client request counts.

## 2. Flexible queries can incur high costs

Clients can select many fields, nest multiple relationships, or request many records in a single operation. This flexibility also opens the door to queries that consume unexpected amounts of resources.

Illustrative example of a wide-ranging query:

```graphql
query LargeReport {
  customers(first: 100) {
    orders(first: 100) {
      items(first: 100) {
        product {
          reviews(first: 100) {
            rating
          }
        }
      }
    }
  }
}
```

If each level returns many items, the number of objects to load and process can grow rapidly. A shallow query can still be very wide; conversely, a deep query is not necessarily expensive if each branch returns little data. Therefore, depth limiting alone is not enough to control every kind of query.

The server should combine several safeguards:

- Paginate lists and enforce a maximum page size limit.
- Limit depth, alias count, or estimated operation complexity where appropriate.
- Set timeouts and resource limits for expensive operations.
- Apply rate limiting per user, application, or API key.
- Monitor operations with abnormal execution times, record counts, or backend costs.
- Consider persisted queries or operation allowlists for controlled clients.

Query complexity is an estimate based on the schema and system policies, not an exact predictor of runtime duration. Fields that call external services, run full-text searches, or perform business computations can have vastly different costs even when the field count looks identical.

In Spring for GraphQL, controls can be placed at the request ingress layer and the GraphQL execution layer, alongside limits at the service or database layers. Never rely solely on the client UI to prevent large queries, since clients can be modified or requests can be sent directly.

## 3. The N+1 problem when resolving fields

A common limitation when implementing GraphQL is the N+1 problem. The server loads a list of N items, and then each item triggers a separate query to load data for a related field.

For example, the following Spring for GraphQL resolver may issue one author query per book:

```java
@SchemaMapping(typeName = "Book", field = "author")
Author author(Book book) {
    return authorRepository.findById(book.authorId()).orElse(null);
}
```

If a query fetches 20 books, the server can execute one query for books plus 20 additional queries for authors. With large lists or multiple levels of relationships, data access counts rise quickly and degrade performance.

Common approaches to address this include:

1. Loading related data in batches instead of item by item.
2. Using DataLoader to collect requests within the same execution into a single batch load and distribute results back to each field.
3. Using Spring for GraphQL's `@BatchMapping` when the field relationship fits the batch mapping model.
4. Optimizing repository and database queries; fetching only needed columns when beneficial.

DataLoader reduces backend call counts, yet it does not replace pagination or query cost limits. A batch containing tens of thousands of keys can still put heavy pressure on the database. DataLoader caches are typically scoped per request execution; do not assume they act as a shared cache across multiple users.

## 4. HTTP and CDN caching is more complex

With REST, each resource usually has its own URL, such as `/books/42`. This enables HTTP caches and CDNs to identify resources by URL, combined with headers like `Cache-Control`, `ETag`, and `Vary`.

With GraphQL, many kinds of data and operations flow through the same endpoint, such as `/graphql`. Two requests to the same endpoint can request completely different data. If only the URL is used as the cache key, the cache can serve the wrong result.

GraphQL caching must account for the operation content, passed variables, user identity or access permissions, and expiration policies. Queries are often sent via POST; some setups support GET for queries to leverage HTTP caching, whereas mutations should never be sent via GET. Persisted queries make operation identification more stable, though variables and authorization context still belong in the cache key.

GraphQL can still leverage caching at multiple layers:

- Caching data in the service or repository layer.
- Caching by operation and input variables when data can be safely shared.
- Client-side caching per field or via normalized entities.
- HTTP/CDN caching when transport, cache keys, and security policies are properly designed.

Keep in mind that caches must respect authorization context. Never share cached responses containing private data between two users just because they sent the same query.

## 5. Security must be enforced down to individual fields

A GraphQL schema can expose multiple paths to the same data. Users can reach a field through different relationships, so checking permissions only at root resolvers is insufficient in many designs.

Suppose an API exposes `me`, `user(id)`, `orders`, and `customer`. If permissions are only checked on the `user` query, another field might inadvertently expose user or order details that the caller is not permitted to view.

Security design must clearly establish:

- Who can invoke an operation, and who can access each object?
- Is the user allowed to view or modify a specific field?
- Do permissions depend on business state, record ownership, or tenant?
- Which internal services can a resolver call, and do those services enforce required authorization checks?

In Spring for GraphQL, you can combine authentication at the HTTP layer, authorization checks on resolvers with Spring Security, and business rule checks inside services. Enforce checks where sufficient context is available to verify permissions on both the object and the action. Never treat hiding fields from the schema or disabling introspection as an authorization mechanism.

Error messages must also be controlled. Internal exceptions, SQL statements, tokens, configuration details, or sensitive data must never appear in responses sent to clients. Access permissions must be verified on the server for every request, including persisted operations.

## 6. Error handling and partial results must be properly understood

A GraphQL response can contain both `data` and `errors`. This happens when some fields resolve successfully while another field fails. Consequently, clients cannot rely solely on HTTP status codes or assume a request only has two binary states: success or failure.

Illustrative response example:

```json
{
  "data": {
    "book": {
      "title": "GraphQL in Practice",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Unable to load author information",
      "path": ["book", "author"]
    }
  ]
}
```

Clients must inspect both `data` and `errors`, then decide whether to render the data that loaded or show a full-screen error. If a field is declared non-null in the schema, an error on that field can propagate up to the nearest parent field that allows `null`; thus, choosing nullable vs. non-null directly affects how much data remains in the response.

On the server, standardize error codes and `extensions` when machine-readable error metadata is needed. Internal logs can retain details for investigation, while client responses should only expose safe, helpful information. With Spring for GraphQL, `DataFetcherExceptionResolver` is one of the extension points for mapping resolver exceptions into structured GraphQL errors.

## 7. Schemas need governance when serving multiple clients

A GraphQL schema is a shared contract between the server and multiple clients. As the number of applications grows, a seemingly small change can impact multiple development teams.

For example, renaming a field or changing a data type can break active queries from older clients. Removing a field as soon as the server stops using it can also break applications that have not yet updated.

To reduce risk:

- Prefer adding new fields in a backwards-compatible manner.
- Mark legacy fields with the `@deprecated` directive and provide a reason or replacement field.
- Monitor field and operation usage before removing legacy API elements.
- Standardize conventions for naming, nullability, pagination, and error structures.
- Test the schema and representative client operations before releasing.

GraphQL provides introspection and an ecosystem of schema-discovery tools, yet those tools do not automatically solve versioning workflows, change notifications, or cross-team release coordination.

## 8. Subscriptions and binary data have distinct requirements

Queries and mutations fit the request-response model well. Subscriptions, by contrast, require a persistent connection or channel so the server can push events to clients. This introduces additional concerns around concurrent connection counts, authentication across the connection lifecycle, reconnects, slow clients, event distribution across multiple instances, and infrastructure scaling.

Subscriptions fit when clients genuinely need continuous updates. For data that does not require real-time delivery, periodic polling or another notification mechanism can be simpler. It is also important to determine which user's permissions govern emitted subscription events and how to handle permission changes after a connection is established.

Core GraphQL does not define a single standard file upload scalar shared across all implementations. Some systems support uploads via multipart extensions, though client and server must agree on the protocol. For large files, a common approach is using GraphQL to create an upload request or issue a pre-signed URL, then transferring the file directly to object storage. This avoids pushing large byte streams through GraphQL resolvers and leverages purpose-built upload mechanisms.

## 9. API operations and observability require richer context

In REST, paths and HTTP methods usually help operations teams identify the kind of action being performed. In GraphQL, many operations share a single endpoint, and field names do not necessarily reflect full backend cost.

If you only count requests hitting `/graphql`, the operations team will struggle to tell which queries are slow, which fields frequently fail, or which resolvers generate excessive database queries. Logging full queries and variables can also expose sensitive data or generate massive log volumes.

A GraphQL system should observe operation names, execution durations, errors, field usage, and durations of key resolvers. Mask or strip sensitive data from logs, enforce request size limits, and preserve tracing from operations down to service or database calls. Persisted operations also help identify common query groups and improve control over known clients.

## 10. When should you choose GraphQL?

GraphQL generally fits well when multiple clients need different combinations of data, data has graph-like relationships, and letting clients pick fields reduces API round trips. It is also useful when a backend team wants to publish a strongly typed schema shared across multiple applications.

REST may be a better fit when the API primarily exposes simple resources, needs direct HTTP/CDN caching, handles large file transfers, or has stable and straightforward endpoint contracts. A system can also use REST for certain flows and GraphQL for screens needing aggregated queries; not every feature has to use the exact same API style.

| Need | What to consider |
| --- | --- |
| Multiple clients needing different field sets | GraphQL can reduce creating separate endpoints per screen |
| Queries with many nested relationships | Requires DataLoader, batch mapping, pagination, and cost limits |
| Public data needing simple CDN caching | REST is usually easier to configure for URL-based caching |
| Different access permissions per field or object | Requires authorization design across resolvers and services |
| Real-time updates | Subscriptions can fit if the system meets long-lived connection needs |
| Large file uploads or downloads | Consider dedicated file transfer flows coordinated via API |

## 11. Checklist before taking GraphQL to production

- [ ] All list fields have pagination and sensible size limits.
- [ ] Query depth, query complexity, or equivalent limiting policies are verified.
- [ ] Relationships with N+1 risk are measured and handled with batch loading where appropriate.
- [ ] Resolvers and services enforce access permissions by user, object, and action.
- [ ] Cache keys account for operation, variables, and authorization context.
- [ ] Clients handle responses containing both `data` and `errors`.
- [ ] The schema has a deprecation and compatibility check process before removing fields.
- [ ] Subscriptions, if present, have authentication, reconnect, and connection limit policies.
- [ ] Logs and tracing identify slow operations or resolvers without leaking sensitive data.

## Conclusion

GraphQL effectively solves letting clients select the data structure they want to receive, yet that flexibility requires the server to tightly control execution cost and access permissions. The key areas to watch when building the API are overly large queries, N+1, caching, field-level security, partial error handling, schema evolution, and subscription operations.

With Spring for GraphQL, resolvers are organized via `@SchemaMapping`, while `@BatchMapping` and DataLoader help batch loading of related data. These tools work best alongside pagination, query limits, authorization checks, error handling, and system observability. Choose GraphQL when the benefits of a typed schema and flexible querying outweigh the operational costs it introduces.
