# Runbook for slow resolvers

Slow resolvers drive up GraphQL execution time, typically manifesting as elevated p95/p99 latency, request timeouts, or specific fields returning slowly even while the endpoint remains healthy. This runbook guides you through isolating bottlenecks from the GraphQL request down to resolvers, databases, and dependent services; choosing load-shedding mitigations; fixing the root cause; and verifying the outcome.

The scope covers Spring for GraphQL applications using Queries, Mutations, Subscriptions, `@SchemaMapping`, `@BatchMapping`, and DataLoader. The procedure focuses on server-side resolvers. If the delay lies in the network, gateway, or client, record that boundary clearly so the issue can be handed off to the right team.

## Goals and diagnostic principles

A GraphQL request passes through multiple layers: HTTP or WebSocket, document parsing and validation, execution planning, data fetcher/resolver invocations, database or external service access, and response serialization. A resolver is only one link in the chain. Never assume a resolver is at fault based solely on total HTTP duration.

During an incident, answer four questions in order:

1. Which requests are slow: which operation, application version, tenant or user cohort, and over what time window?
2. Where is the time spent: server queuing, field execution, database, external services, or response serialization?
3. What drives the cost growth: list element count, query depth, number of backend calls, response size, or concurrency level?
4. What change reduces latency while preserving data accuracy, access controls, and API behavior?

Prefer correlated traces and metrics. A single log line reading "resolver took 2 seconds" is insufficient without the operation, field path, trace ID, and dependency timings.

## Symptoms that trigger this runbook

- GraphQL endpoint p95 or p99 breaches its SLO without a matching rise in traffic.
- One specific operation or field becomes slow while other operations remain normal.
- Response time scales with returned element count—for instance, querying 10 records is fast while 100 records is very slow.
- SQL query counts or external service calls grow nearly linearly with the number of objects in the response.
- CPU, connection pools, worker pools, or queues climb high; requests start timing out or getting canceled.
- Responses contain `errors` or partial data due to resolver/dependency timeouts, errors, or rejections.

For Subscriptions, distinguish subscription setup time, per-event latency, and stream consumption rate. Never use short-lived HTTP request p95 to judge whether a long-lived subscription is healthy.

## 15-step troubleshooting procedure

### 1. Confirm scope and impact

Record the start time, breached SLO, percentage of affected requests, endpoint, environment, application version, and recent deployments. Determine whether the incident affects the entire GraphQL API or only one operation/field. Compare against the same-time-of-day baseline to avoid mistaking normal traffic peaks for an incident.

If failures are spreading, prioritize service recovery: shed load on the offending operation, cap concurrency, or roll back the relevant release following your operational procedures. Record every mitigation and its timestamp so metrics can be correlated later.

### 2. Capture a representative request

Select a reproducible slow request and record:

- `operationName`, operation type, and document hash or persisted query ID.
- Suspected field path, such as `Query.books[12].author`.
- Trace ID, request ID, timestamp, application version, and anonymized tenant.
- Item count, depth, and response shape; strip sensitive values from `variables`.
- Total duration, HTTP status, GraphQL error count, and whether the request timed out or was canceled.

Never log access tokens, cookies, passwords, personal data, or full `variables`. When reproducing, use synthetic data or sanitized fixtures that preserve the slow query's shape.

### 3. Separate client, gateway, and application time

Compare client-measured duration against gateway and server timings. If the client sees 4 seconds while the server records only 300 ms, check the network, proxies, gateway queues, and response transfer. If the server also takes nearly 4 seconds, continue following the trace inside the application.

Ensure clocks are synchronized and trace context propagates across the gateway. Clock skew or broken traces can make span ordering misleading.

### 4. Open the GraphQL request trace

Spring for GraphQL integrates Micrometer Observation. Instrumentations such as `GraphQlObservationInstrumentation` and `DataFetcherObservationInstrumentation` can provide request-level and data-fetcher-level observations depending on your Spring for GraphQL version and `GraphQlSource` configuration. With Spring Boot, inspect which instrumentation is actually auto-configured or explicitly configured in the application; avoid duplicate registration.

Open a slow trace and locate the longest span. Identify whether that span is parsing/validation, a data fetcher, JDBC, an HTTP client, or another task. If the trace has only a top-level HTTP span, add data fetcher and dependency observations before guessing from scattered logs.

Observation, span, and tag names can vary across versions or custom conventions. Use the actual names emitted by your application's telemetry; do not build dashboards around assumed tag names.

### 5. Isolate the field path and resolver

Look for data fetchers with long durations, unusual invocation counts, or many child spans. Field coordinates such as `Book.author` identify the corresponding resolver. Cross-reference with the schema and controller handling that field:

- `@QueryMapping` or `@MutationMapping` for root operation fields.
- `@SchemaMapping` for fields resolved from a parent object.
- `@BatchMapping` for batch-loading the same field across multiple objects.

An operation can invoke the same resolver many times across many objects. Always examine total time, invocation count, and average time per call. A 5 ms resolver executed 200 times hurts more than a 300 ms resolver called once.

### 6. Inspect database query counts and timings

Correlate the trace with connection pool and database metrics. Check SQL statements per request, per-statement duration, rows read/returned, lock waits, connection waits, and query plans. Look for patterns:

- Similar queries repeating per object.
- Filter or join queries missing an appropriate index.
- Fetching too many columns or rows when GraphQL needs only a subset.
- Many small sequential queries instead of a single query by ID set.
- Connection pool exhaustion causing resolvers to spend most of their time waiting for a connection.

Run database `EXPLAIN` tools in an appropriate environment with safe permissions. Where supported, review execution plans and buffer/read statistics; do not run full-execution analyze commands in production if they could cause unexpected load or locks.

### 7. Inspect dependent services

If the resolver calls REST, gRPC, search, cache, or internal services, inspect child spans, DNS, connection pools, timeouts, retries, and error rates. Automatic retries can multiply calls when a dependency is overloaded. Confirm the dependency timeout is shorter than the request's remaining time budget and retries are bounded.

If multiple resolvers call the same service, check whether requests can be batched, routed through a bulk API, or reused within the request scope. Never share caches across users if data depends on permissions or tenant.

### 8. Check application saturation

Correlate latency with CPU, heap, GC pauses, thread/worker pools, queues, connection pools, and active request counts. A synchronous resolver can hold a thread while waiting on I/O. In WebFlux applications, calling blocking APIs directly on the event loop can slow down many concurrent requests at once.

Check logs for thread starvation, rejected tasks, timeouts, and pool exhaustion. Once resources are saturated, raising timeouts usually just holds requests and connections longer. First reduce concurrency or traffic causing the load, then fix the source of waiting.

### 9. Classify the primary root cause

Select the category with the clearest evidence:

| Cause category | Common symptoms | First mitigation/fix |
|---|---|---|
| N+1 | SQL or backend call counts grow with object count | Batch loads with `@BatchMapping` or DataLoader |
| Poor query | A few SQL statements dominate total time | Fix indexes, joins, projections, or query plans |
| Slow dependency | Long HTTP/gRPC/search spans or rising retries | Proper timeouts, bulk APIs, bounded retries, dependency remediation |
| Resource saturation | Rising pool waits, queues, GC, or CPU | Reduce concurrency/load and fix the bottleneck |
| Overly broad query | Deeply nested fields, large lists, large responses | Pagination, depth/complexity limits, and page size caps |
| In-resolver work | CPU profile shows computation/serialization dominating time | Reduce repeated computation, optimize data structures and payloads |

Multiple causes may coexist. Pick the single highest-impact cause to fix first, then re-measure because removing the first bottleneck often exposes the next one.

### 10. Apply controlled mitigations

While preparing a fix, consider temporarily throttling the heavy operation, shrinking page sizes, lowering concurrency to the dependency, disabling an optional data section, or rolling back a recent change. Apply these only within what API contracts and operational procedures allow.

For Mutations, never retry automatically just because the client received a timeout: the mutation may already have committed on the server. Require an idempotency key or status-checking mechanism before retrying. For Queries, retries must also be bounded and must not amplify load while a dependency is degraded.

### 11. Fix N+1 with `@BatchMapping` or DataLoader

N+1 typically occurs when a child-field resolver fetches data individually for each parent object. For example, querying 50 books and resolving each book's author individually can produce 1 query for books and 50 queries for authors.

An individual resolver can look deceptively simple:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
Author author(Book book) {
    return authorService.findById(book.authorId());
}
~~~

When data can be batch-loaded, switch to `@BatchMapping`:

~~~java
@Controller
class BookController {

    private final AuthorService authorService;

    BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    Map<Book, Author> author(List<Book> books) {
        Set<UUID> authorIds = books.stream()
                .map(Book::authorId)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());

        Map<UUID, Author> authors = authorService.findByIds(authorIds);
        Map<Book, Author> result = new HashMap<>();
        for (Book book : books) {
            Author author = book.authorId() == null
                    ? null
                    : authors.get(book.authorId());
            result.put(book, author);
        }
        return result;
    }
}
~~~

This example assumes `Book` is a record with `authorId()`, and `AuthorService.findByIds` runs a single query over the ID set and returns a map keyed by ID. Adapt types to your actual domain. `@BatchMapping` is a convenient declarative way for Spring for GraphQL to register a batch loader; DataLoader groups keys requested within the same request execution and maps results back to the right source objects.

When implementing, verify these points:

- The batch query genuinely reduces SQL/backend calls rather than hiding an N+1 loop inside `findByIds`.
- Results map accurately back to each source object; explicitly handle missing data or null IDs.
- Batching still enforces tenant filters and access permissions. Never leak another tenant's data merely because an ID appeared in the same batch.
- Request-scoped DataLoader caching fits the data and authorization rules. Avoid sharing caches across requests or users when results can differ.
- Do not leave two resolvers registered for the same field, such as keeping the old `@SchemaMapping` while adding `@BatchMapping` for `Book.author`.
- If batches grow very large, chunk them within database or downstream service limits.

`@BatchMapping` fits when multiple parent objects need the same field. For more complex relationships or loading patterns, use `BatchLoaderRegistry` and explicit DataLoaders while preserving request-scoped batching and accurate key/order mapping.

### 12. Optimize resolvers and I/O boundaries

After eliminating N+1, review what the resolver itself does:

- Fetch only required columns; use projections or queries tailored to what is actually returned.
- Paginate lists; avoid loading an entire relationship only to slice it in Java.
- Move shared business logic into services so it can be measured, tested, and reused.
- Avoid calling `.block()` or blocking operations on the WebFlux event loop. Choose reactive APIs end to end or isolate blocking work onto an appropriate scheduler.
- Do not hold database transactions open while waiting on external service calls. Keep transactions short around database operations requiring consistency.
- Bound concurrency when calling multiple dependencies; unbounded parallelism can overwhelm downstream systems further.
- Use caching only with explicit policies for TTL, invalidation, tenants, and access permissions.

Never optimize by serving stale data or skipping permission checks just to hit lower latency. If stale-while-revalidate or caching is needed, explicitly define which fields tolerate stale data and for how long.

### 13. Limit GraphQL query cost

A single operation can request deeply nested fields and huge lists. Combine safeguards:

- Pagination with bounded page sizes; validate limits server-side rather than trusting client-supplied values.
- Bound query depth and complexity to match schema and backend capacity.
- Use persisted queries or allowlists where appropriate for the product model.
- Set request and dependency timeouts; propagate consistent time budgets across layers.
- Monitor response size and resolved object counts, not only requests per second.

Depth limits alone do not block every expensive query: a single field can be very costly even in a shallow query. Complexity analysis should account for list multiplicity, field costs, and page limits. Error messages should be clear enough for clients to notice limit breaches without exposing internal details.

### 14. Verify before and after release

Re-run the exact representative operation with matching data shape and concurrency. Compare before and after:

| Metric | Expected after fix |
|---|---|
| Operation p50, p95, p99 | Drops and stabilizes below SLO |
| Resolver invocations per field | Does not grow with object count once batched |
| SQL/backend calls per request | Drops as expected |
| Database/connection pool wait | Does not spike abnormally |
| CPU, heap, GC, and thread pools | Introduces no new bottleneck |
| GraphQL errors and returned data | No error increase; results and permissions stay accurate |

Test empty lists, single items, multiple items, missing IDs, non-existent records, and multi-tenant cases. For DataLoader, verify batches fire the expected number of times and results attach to the right source objects. Run load tests or staging checks with production-like data distributions; never infer effectiveness from a single isolated request.

Roll out via canary or traffic cohorts if the platform supports it. Watch the modified operation and field, and set explicit rollback thresholds. If latency drops yet error rate, DB load, or memory jumps sharply, the fix is not ready.

### 15. Close the incident and prevent recurrence

Document the root cause, trace/metric evidence, affected operations, deployed changes, mitigations, and before/after numbers. File follow-up work for remaining gaps such as other queries sharing the same N+1 pattern, missing pagination, or dependencies lacking timeouts.

Add dashboards and alerts by operation/field with operational value. Keep metric labels low cardinality: standardized operation names, field coordinates, or endpoint groups. Never attach raw queries, variables, user IDs, or arbitrary values to metric labels. For sensitive queries, store query hashes and sanitized metadata.

## On-call incident checklist template

- [ ] Confirm the affected operation, time window, SLO, and impacted users.
- [ ] Capture a trace ID and a reproducible request stripped of sensitive data.
- [ ] Separate client/gateway time from server time.
- [ ] Locate the slowest data fetcher span and field path.
- [ ] Correlate SQL counts, query plans, connection waits, and dependency spans.
- [ ] Inspect CPU, GC, thread/worker pools, and queues.
- [ ] Identify N+1, poor queries, slow dependencies, saturation, or overly broad queries.
- [ ] Apply controlled mitigations if impact is spreading.
- [ ] Re-measure after the fix with the same query shape and concurrency.
- [ ] Verify data accuracy, access permissions, GraphQL errors, and SLOs before closing.

## Operational pitfalls to avoid

**Only raising timeouts:** this can make requests hold threads, connections, and memory longer while the underlying bottleneck remains.

**Looking only at endpoint latency:** total latency does not reveal which field or dependency caused the slowdown. Add tracing around data fetchers and I/O calls.

**Batching without reducing query count:** a batch loader can still call a repository once per ID inside a loop. Measure actual SQL statement counts after the change.

**Caching without considering permissions:** shared caches can serve data to the wrong tenant or wrong user. Cache scope must match data and authorization boundaries.

**Unbounded retries:** retries amplify load and can worsen dependency outages. For mutations, retries also risk executing actions twice.

**Tagging metrics with free-form data:** raw queries, variables, and IDs explode cardinality, bloat telemetry memory, and risk leaking sensitive data.

## Completion criteria

Close this runbook only when the slowdown location is identified with traceable evidence; the fix or mitigation is documented; latency and load have been re-measured; GraphQL results and access controls remain intact; and owners/tasks are assigned for remaining risks. If the root cause is not yet found, document what telemetry is missing and concrete actions to capture evidence on the next reproduction.
