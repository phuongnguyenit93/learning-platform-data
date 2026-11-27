# Production Readiness Checklist

Taking a Spring for GraphQL API to production requires much more than an endpoint returning valid JSON. The schema must be stable, resolvers must handle load, every field must protect the right data, queries must have cost limits, errors must be handled safely, and operations teams must be able to trace requests from GraphQL down to databases or downstream services.

This hands-on practice provides a checklist for reviewing a GraphQL service prior to release and during operations. Each item requires concrete evidence such as configuration, tests, dashboards, traces, runbooks, or drill results. A checkbox is marked complete only when verifiable evidence exists and an owner is assigned.

## 1. How to Use This Checklist

Conduct the review against production or a staging environment configured identically to production. For each item, record the status, evidence, owner, and remaining gaps. Never use a single test run on small data to conclude the system can handle production load.

| Status | Meaning |
|---|---|
| `PASS` | Verified with appropriate evidence |
| `FAIL` | Checked and found non-compliant |
| `N/A` | Not applicable; justification must be recorded |
| `TODO` | Not yet checked or insufficient evidence |

Severity classification:

- **Release blocker:** risk that could leak data, break the API contract, cause data loss, or prevent safe service operation. Do not release while any blocker remains unresolved without an approved risk acceptance decision.
- **High:** can cause significant degradation, elevated errors, or difficult recovery. Requires mitigation, an owner, and a clear due date before release.
- **Operational:** improves observability, maintainability, and recovery; must be placed on the operational roadmap.

Do not mark `N/A` merely due to lack of time. If a capability is unused—for example, Subscriptions—explicitly note that the transport is disabled and verify no corresponding route is exposed.

## 2. Schema and API Contract

The SDL schema is the contract between client and server. A schema change can impact many clients even if server code compiles cleanly.

- [ ] **Release blocker** — Schema is stored and versioned alongside source code; changes are reviewed and have a diff history.
- [ ] **Release blocker** — Type, field, argument, input, and enum names match the domain consistently; no table names, internal structures, or secrets are exposed.
- [ ] **Release blocker** — Nullability accurately reflects data availability. For `T!` fields, the server guarantees a non-null value in all valid cases.
- [ ] **High** — Large lists are paginated; page size limits are validated server-side with a reasonable maximum.
- [ ] **High** — Mutations define clear input types and enforce input validation and business rules server-side.
- [ ] **High** — Old fields/arguments are deprecated prior to removal, with a client migration plan and sunset timeline.
- [ ] **High** — Schema changes are compatibility-checked against active clients/queries, including persisted operations if used.
- [ ] **Operational** — Field, enum, and input descriptions clearly communicate semantics, units, limits, and null behavior to clients.
- [ ] **Operational** — Schema review workflow has designated owners and clear acceptance criteria for breaking changes.

Pay special attention to nullability errors. If a resolver returns `null` for a non-null field, GraphQL can propagate the error to the parent and nullify a large portion of the response. Test missing data, dependency failures, and access-denied scenarios against the schema's nullability rules.

## 3. Spring for GraphQL Application Configuration

Verify how the application actually constructs `GraphQlSource`, registers schemas, and binds resolvers. With Spring Boot, confirm that auto-configurations are being used rather than adding duplicate configuration copied from another version's example.

- [ ] **Release blocker** — The application starts up and loads the entire SDL schema cleanly; schema errors are caught at build/startup or in deployment tests.
- [ ] **Release blocker** — Every field has an explicit resolver or can be safely resolved by the default property data fetcher.
- [ ] **Release blocker** — No two data fetchers compete for the same field due to duplicate `@SchemaMapping`, `@QueryMapping`, `@MutationMapping`, or `@BatchMapping` registrations.
- [ ] **High** — Profile-specific GraphQL configurations are verified; production does not accidentally enable local/dev debug settings.
- [ ] **High** — Custom scalars, directives, instrumentations, and exception resolvers are registered exactly once.
- [ ] **High** — HTTP request size limits, timeouts, and server settings match expected GraphQL payloads.
- [ ] **Operational** — Spring Boot, Spring for GraphQL, and GraphQL Java versions are managed consistently; upgrades include compatibility tests.

The GraphQL endpoint typically accepts HTTP POST; if the application uses WebSocket for Subscriptions, verify that endpoint and handshake separately. Enable only the transports genuinely needed. Never assume an HTTP test validates WebSocket or other transports.

## 4. Endpoint Security and Network Configuration

GraphQL exposes a centralized endpoint, yet each operation and field still needs proper access control. Protecting the endpoint at the HTTP layer is the first line of defense.

- [ ] **Release blocker** — Production accepts connections only over HTTPS/TLS per infrastructure standards.
- [ ] **Release blocker** — Spring Security protects the GraphQL endpoint properly; anonymous access is permitted only for explicitly designated public operations.
- [ ] **Release blocker** — CORS uses an explicit origin allowlist; wildcard origins are never combined with credentials.
- [ ] **Release blocker** — If authenticating via cookies/sessions, CSRF is handled appropriately for the authentication mechanism and transport. Never disable CSRF just to make a GraphQL request work.
- [ ] **High** — Request body size, header size, and request rate limits are enforced at the gateway/server.
- [ ] **High** — GraphiQL, GraphQL Playground, debug endpoints, and developer UIs are not publicly exposed unintentionally.
- [ ] **High** — Secrets, signing keys, database passwords, and service tokens come from a secret manager or environment secret store; none are committed to the repository.
- [ ] **High** — Security headers, proxies, and forwarded headers are configured properly for the deployment topology; client-spoofed headers are never trusted.
- [ ] **Operational** — Credential rotation and token revocation procedures exist for incidents.

**Note:** CORS is not an authentication or authorization mechanism. It primarily controls which browser JavaScript origins are allowed to read responses. The API must still verify identity and permissions server-side.

## 5. Authentication and Field-Level Authorization

A user may be allowed to call `Query.account` yet not allowed to view every nested field beneath it. Authorization must be enforced at data and action boundaries, even when clients craft custom queries outside the official UI.

- [ ] **Release blocker** — Principal identity is established from trusted sources; never accept `userId`, roles, or trusted tenants from GraphQL variables to determine identity.
- [ ] **Release blocker** — Every sensitive Query, Mutation, and field checks appropriate permissions.
- [ ] **Release blocker** — Object access is verified by owner, tenant, or business relationship; knowing an ID does not grant read access to the object.
- [ ] **Release blocker** — Mutations check permissions on the target object and specific action, not merely permission to call the endpoint.
- [ ] **High** — Security rules live in the service/domain layer or method security so they cannot be bypassed when the same service is invoked from REST, message handlers, or jobs.
- [ ] **High** — Fields returning sensitive data have tests for anonymous users, valid users, cross-tenant users, and unauthorized users.
- [ ] **High** — Access-denied responses follow product policy: return an appropriate error or conceal resource existence when required.
- [ ] **High** — Permissions are checked on each Subscription event when permissions or object state can change while the stream is open.
- [ ] **Operational** — Audit logs for critical actions record actor, action, target, and timestamp without logging credentials or sensitive payloads.

You can use Spring Security method security, such as `@PreAuthorize`, on resolvers or services. Regardless of placement, trace all call paths. An annotation on a resolver does not protect a service if that service is called via another path; conversely, protecting only the service does not replace field-level authorization when a resolver aggregates multiple data sources.

## 6. Validation, Errors, and Input Data

GraphQL checks syntax, types, and operation structure, but does not automatically know all application business rules.

- [ ] **Release blocker** — Inputs are validated on the server: string lengths, value ranges, formats, collection size limits, and required fields.
- [ ] **Release blocker** — Business rules and current state are checked before persisting data.
- [ ] **Release blocker** — Stack traces, SQL, internal hostnames, file paths, secrets, or raw exception messages are never returned to production clients.
- [ ] **High** — Expected errors are mapped to GraphQL errors with stable codes/extensions and actionable messages.
- [ ] **High** — Unexpected system errors are logged server-side with a trace ID; clients receive a generic message.
- [ ] **High** — Decisions between partial data and fail-fast behavior are defined per field, nullability, and business requirements.
- [ ] **High** — Mutations have an idempotency strategy when clients may retry after timeouts or disconnects.
- [ ] **Operational** — Error codes and API documentation are standardized so clients do not have to parse free-form message text.

Spring for GraphQL supports exception handling via `DataFetcherExceptionResolver`/`DataFetcherExceptionResolverAdapter` and `@GraphQlExceptionHandler` where appropriate for your version. Do not let multiple handlers produce conflicting error mappings. Distinguish validation errors, business errors, authorization errors, and dependency failures.

Example response containing both `data` and `errors`:

```json
{
  "data": {
    "book": {
      "id": "b-101",
      "title": "Spring in Practice",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Unable to load author information",
      "path": ["book", "author"],
      "extensions": {
        "code": "AUTHOR_LOOKUP_FAILED"
      }
    }
  ]
}
```

This is an illustrative error contract example; actual HTTP status codes, `data`, and error contents depend on the transport, error type, and server configuration. Never treat HTTP 200 as proof that an operation succeeded completely; clients must inspect `errors`.

## 7. Query Cost Control and Abuse Prevention

GraphQL lets clients choose fields, nest relationships, and use aliases. A single request can generate more work than many typical REST requests combined.

- [ ] **Release blocker** — All lists enforce a maximum page size on the server.
- [ ] **Release blocker** — Query depth and/or query complexity have limits tailored to the schema and data.
- [ ] **Release blocker** — Requests have timeouts; dependency and database waits stay within the request budget.
- [ ] **High** — Limits exist for request size, input element counts, alias counts, or query patterns that cause massive fan-out.
- [ ] **High** — Rate limits are applied per principal, client, or IP as appropriate; expensive operations may require cost-based limiting.
- [ ] **High** — Persisted queries/allowlists are considered for clients with known operation sets; the server safely rejects disallowed queries.
- [ ] **High** — Introspection is governed according to product requirements and threat model; disabling introspection is not treated as a substitute for authorization.
- [ ] **Operational** — Dashboards track query cost, depth, page size, response bytes, and rejection rates due to limit violations.

Depth limits alone cannot stop every expensive query. A field can return thousands of items even in a two-level query. Complexity should account for item counts, pagination, high-cost fields, and fan-out relationships. Exact instrumentations/validators depend on the GraphQL Java version and `GraphQlSource` configuration; verify they actually run before release.

## 8. Resolver Performance, N+1, and DataLoader

Resolvers must do bounded work and access backends efficiently. Measure on realistic query shapes, since resolvers only execute when their fields are requested.

- [ ] **Release blocker** — Common operations are load-tested with production-like record counts, concurrency, and query shapes.
- [ ] **High** — Relationship fields do not produce N+1 queries; `@BatchMapping` or `DataLoader` is used when multiple source objects need the same kind of data.
- [ ] **High** — Batch loaders genuinely query by key set rather than calling single-item repository methods inside a loop.
- [ ] **High** — Batch results are mapped back to the right source/key without relying on unguaranteed database ordering.
- [ ] **High** — Batch sizes and bind parameter counts are bounded; root lists are paginated.
- [ ] **High** — Unnecessary columns/relationships are not loaded; query plans and indexes are verified for critical queries.
- [ ] **High** — Resolvers do not hold database transactions open while waiting on external dependencies unnecessarily.
- [ ] **High** — In WebFlux, blocking APIs are not called directly on event-loop threads; blocking work is isolated to an appropriate scheduler or replaced with reactive APIs.
- [ ] **High** — Parallel dependency calls have bounded concurrency and timeouts to avoid uncontrolled fan-out.
- [ ] **Operational** — Caches have explicit TTLs, invalidation, and tenant/authorization scoping so user data is never leaked across users.

Example batch resolver:

```java
@BatchMapping(typeName = "Book", field = "author")
Map<Book, Author> author(List<Book> books) {
    Set<UUID> authorIds = books.stream()
            .map(Book::authorId)
            .filter(Objects::nonNull)
            .collect(Collectors.toSet());

    Map<UUID, Author> authors = authorService.findByIds(authorIds);
    Map<Book, Author> result = new HashMap<>();

    for (Book book : books) {
        result.put(book, book.authorId() == null
                ? null
                : authors.get(book.authorId()));
    }
    return result;
}
```

This example assumes `findByIds` executes a bulk query, enforces tenancy/authorization, and returns a map keyed by ID. If the service still calls `findById` per item, N+1 remains. Measure SQL counts and backend call counts to prove effectiveness.

DataLoader typically serves batching and key caching within a single GraphQL execution. Never turn a per-request cache into a cache shared across users. When data mutates within the same request or with custom loaders, review cache clearing/priming policies and consistency guarantees.

## 9. Databases and Downstream Dependencies

- [ ] **Release blocker** — Connection pools are bounded; pool wait times and timeouts are monitored.
- [ ] **High** — Critical queries have appropriate indexes and execution plans verified against realistic data volumes.
- [ ] **High** — All HTTP/gRPC dependencies have appropriate connect/read/response timeouts.
- [ ] **High** — Retries are bounded, use backoff, and apply only to retry-safe operations.
- [ ] **High** — Circuit breakers/bulkheads are considered for fragile dependencies so load is not amplified when targets are overloaded.
- [ ] **High** — Transactions are short-lived, use appropriate isolation levels, and do not wrap long external calls.
- [ ] **High** — Mutations handle write contention, unique constraints, and data integrity at the database level.
- [ ] **Operational** — Dashboards cover pool usage, slow queries, lock waits, dependency latency, timeouts, and error rates.

GraphQL-level timeouts do not replace database or HTTP client timeouts. When a request is cancelled, verify whether cancellation propagates to underlying work; otherwise backends may keep consuming resources after the client disconnects.

## 10. Mutations and Consistency

Mutations often cause side effects that cannot be rolled back automatically. Clients may time out even when the server committed successfully, so retries must be designed explicitly.

- [ ] **Release blocker** — Every mutation clearly identifies the actor, target resource, and required permissions.
- [ ] **Release blocker** — Transactions have clear commit/rollback rules; success is never returned before mandatory operations complete.
- [ ] **Release blocker** — Idempotency controls or result-lookup mechanisms exist when clients retry operations with side effects.
- [ ] **High** — Input validation and domain validation run before persisting data.
- [ ] **High** — Duplicate requests, optimistic locking, or update conflicts are handled according to business requirements.
- [ ] **High** — Events are published post-commit or via a transactional outbox when database and message broker consistency is required.
- [ ] **Operational** — Audit trails record critical mutations and their outcomes.

Never blindly retry a mutation simply because the client missed a response. First determine whether the server already executed it. For payments, order creation, or state transitions, idempotency keys should be validated on the server with appropriate storage constraints.

## 11. Subscriptions and Long-Lived Connections

If the module does not provide Subscriptions, mark `N/A` and confirm production does not expose the corresponding transport. If it does, review connection and event lifecycles separately.

- [ ] **Release blocker** — Transport and subprotocol are explicitly configured; only policy-approved clients/origins may connect.
- [ ] **Release blocker** — Connection authentication and subscription/event authorization are verified; expired or revoked tokens have defined behavior.
- [ ] **Release blocker** — Data access permissions are re-evaluated as events are emitted, especially when membership/tenant/role can change.
- [ ] **High** — Connection counts and subscription counts per principal/client are bounded.
- [ ] **High** — Heartbeat, idle timeout, reconnect, and graceful shutdown strategies are in place.
- [ ] **High** — Backpressure or queue limits prevent slow clients from growing server memory unboundedly.
- [ ] **High** — Subscriptions close and release resources when clients disconnect or lose permissions.
- [ ] **Operational** — Metrics track active connections, event rates, dropped events, queue sizes, and subscription lifetimes.
- [ ] **Operational** — Across multiple instances, pub/sub or event distribution delivers events to the right subscribers per the deployment architecture.

Do not use short HTTP response times to judge the health of long-lived subscriptions. Measure event latency, connection counts, and consumption rates independently.

## 12. Pre-Release Testing

A test suite covering only happy paths is insufficient for production GraphQL. Tests must cover operations, nested fields, partial errors, and resource limits.

- [ ] **Release blocker** — Unit tests cover critical domain/service logic and authorization rules.
- [ ] **Release blocker** — Integration tests load the real schema and execute critical Queries/Mutations.
- [ ] **Release blocker** — Tests cover anonymous users, valid users, missing permissions, wrong tenants, and missing objects.
- [ ] **Release blocker** — Tests verify nullability, failing resolvers, partial data, and GraphQL `errors`.
- [ ] **High** — N+1 tests verify batch loaders run properly and SQL/backend call counts drop.
- [ ] **High** — Tests cover pagination, maximum page sizes, query depth/complexity, and limit-exceeding requests.
- [ ] **High** — Tests cover dependency timeouts, unavailable databases, retries, and cancellations.
- [ ] **High** — Tests cover duplicate/retried mutations and concurrent update conflicts.
- [ ] **High** — Load and soak tests run with production-like concurrency, payloads, and data distributions.
- [ ] **High** — If Subscriptions are enabled, tests cover auth, reconnects, slow clients, disconnects, and multi-instance delivery.
- [ ] **Operational** — Post-deploy smoke tests verify health, schema availability, and critical operations.

Example test using `GraphQlTester`:

```java
graphQlTester.document("""
        query Books($first: Int!) {
            books(first: $first) {
                id
                title
                author { id name }
            }
        }
        """)
    .variable("first", 20)
    .execute()
    .path("books")
    .entityList(BookView.class)
    .hasSize(2);
```

`BookView` is an application test DTO; the test fixture has two books, so the assertion uses `hasSize(2)`. This test illustrates checking pagination and relationship fields; add assertions for data values, errors, permissions, and repository call counts. `GraphQlTester` can be configured directly or over HTTP depending on whether you are testing resolvers/schema or the full transport/security chain.

## 13. Observability: Logs, Metrics, and Traces

Production readiness requires answering which operations are slow, which fields fail, and which dependencies dominate latency without enabling sensitive verbose logging broadly.

- [ ] **Release blocker** — Every request carries a correlation/trace ID across gateway, GraphQL, services, and dependencies.
- [ ] **High** — Metrics track request count, error rate, p50/p95/p99 latency, and throughput.
- [ ] **High** — Observations are broken down by operation and data fetcher/field with bounded cardinality.
- [ ] **High** — Traces include resolver spans and critical child spans such as JDBC, HTTP clients, or gRPC.
- [ ] **High** — Dashboards display connection pools, thread/worker pools, CPU, heap, GC, queues, and dependency health.
- [ ] **High** — Logs include operation name/hash, trace ID, and error code; access tokens, cookies, raw variables, and PII are never logged.
- [ ] **High** — Metric labels never include user IDs, raw queries, variables, arbitrary URLs, or high-cardinality values.
- [ ] **High** — Sampling is configured to retain traces for errors and slow requests per observability policy.
- [ ] **Operational** — Dashboards separate total latency from resolver, database, and dependency latency.
- [ ] **Operational** — Telemetry retention, access control, and redaction comply with data governance policies.

Spring for GraphQL integrates with Micrometer Observation. Observations/instrumentations can be used at the GraphQL request and data-fetcher levels; exact observation names, tags, and availability depend on library versions and `GraphQlSource` configuration. Inspect actual traces in staging. Do not assume tag names in documentation examples match your application's tags.

## 14. Deployment, Environment Configuration, and Rollback

- [ ] **Release blocker** — Artifacts are built from reviewed commits; dependencies and container images are versioned.
- [ ] **Release blocker** — Production secrets and configurations are injected from a configuration/secret manager, never baked into images.
- [ ] **Release blocker** — Database migrations are compatible with deploy/rollback strategies; breaking migrations follow a multi-step plan.
- [ ] **High** — Liveness and readiness probes distinguish process liveness from readiness to receive traffic.
- [ ] **High** — Graceful shutdown stops accepting new requests, gives in-flight requests reasonable time to finish, and closes subscriptions/connections cleanly.
- [ ] **High** — CPU, memory, replica counts, and autoscaling are tested under expected load.
- [ ] **High** — Canary/rolling deployments enforce health gates; schemas and resolvers stay compatible across coexisting versions during rollout.
- [ ] **High** — A rehearsed rollback procedure exists with clear activation criteria.
- [ ] **Operational** — Config drift between staging and production is detected; configuration changes are reviewed.

Specifically for GraphQL schemas, clients can start requesting new fields as soon as a subset of replicas updates. Rollouts must ensure gateways/load balancers do not route new queries to replicas lacking the new schema/fields, or follow a compatible rollout sequence.

## 15. SLOs, Alerting, and Operational Runbooks

- [ ] **Release blocker** — Latency and availability SLOs exist for critical operations.
- [ ] **High** — Alerts are based on error budgets/SLO burn or meaningful thresholds, avoiding pages on brief spikes.
- [ ] **High** — Alerts cover p95/p99 latency, error rates, timeouts, saturation, connection pool exhaustion, and dependency failures.
- [ ] **High** — Dashboards distinguish client errors (validation/authorization/rate limits) from server/dependency errors.
- [ ] **High** — Runbooks exist for slow resolvers, N+1 regressions, slow databases, dependency timeouts, error-rate spikes, and Subscription degradation where applicable.
- [ ] **High** — Alert recipients, escalation paths, and on-call contacts are clearly defined.
- [ ] **Operational** — Post-incident review and action-item tracking processes are established.
- [ ] **Operational** — Recovery and rollback drills are run periodically.

Alert by normalized operation name or field coordinate. Avoid alerts or metric labels keyed by raw query text or free-form inputs, which can grow cardinality without bound.

## 16. Release Gate Decision

Before signing off, aggregate findings by category. Never average scores to hide an unresolved release blocker.

| Category | Acceptance Criteria |
|---|---|
| Schema/API | No unscheduled breaking changes; nullability and pagination verified |
| Security | Endpoint, authentication, field authorization, tenant isolation, and secret handling meet requirements |
| Correctness | Queries, Mutations, error mapping, and partial data have adequate tests |
| Performance | Query costs bounded; N+1 addressed; load and dependency budgets meet SLOs |
| Reliability | Timeouts, pools, retries, cancellation, health probes, and graceful shutdown verified |
| Observability | Dashboards, traces, alerts, and runbooks suffice to detect and isolate incidents |
| Operations | Rollout, rollback, migrations, and on-call ownership confirmed |

Release decision:

- **GO:** all release blockers are `PASS`; remaining High items have owners, due dates, and accepted mitigations; rollback is ready.
- **NO-GO:** any release blocker is `FAIL`/`TODO`, data access controls are unproven, or severe incidents cannot be detected and recovered.
- **GO WITH ACCEPTED RISK:** used only when an authorized owner formally records remaining High items, impact, mitigations, due dates, and stop/rollback triggers. Never use this status to waive a release blocker.

## 17. Readiness Sign-Off Template

You can copy this template into a release ticket or review document:

```text
Service:
Environment:
Release/version:
Commit:
Review date:
Reviewer:

Schema/API: PASS | FAIL | TODO | N/A
Security: PASS | FAIL | TODO | N/A
Validation/errors: PASS | FAIL | TODO | N/A
Query cost/performance: PASS | FAIL | TODO | N/A
Database/dependencies: PASS | FAIL | TODO | N/A
Mutation/consistency: PASS | FAIL | TODO | N/A
Subscription (if enabled): PASS | FAIL | TODO | N/A
Tests/load: PASS | FAIL | TODO | N/A
Observability: PASS | FAIL | TODO | N/A
Deployment/rollback: PASS | FAIL | TODO | N/A
SLO/runbooks/on-call: PASS | FAIL | TODO | N/A

Release blockers:
Accepted risks (owner, due date, mitigation):
Evidence links:
Rollback trigger and procedure:
Decision: GO | NO-GO | GO WITH ACCEPTED RISK
Approver:
```

The record must point to concrete evidence such as pipeline runs, test reports, dashboards, traces, security reviews, or runbooks. Never mark `PASS` based solely on verbal confirmation.

## 18. Comprehensive Practice

Apply this checklist to a sample Spring for GraphQL service or one currently under development:

1. Select the three most critical operations, including at least one Query and one Mutation. If Subscriptions exist, include one event stream as well.
2. List sensitive fields and trace paths from principal to resolver, service, and database. Verify tenant/owner checks on every read and write path.
3. Run queries with nested relationships over sufficiently large lists. Measure SQL counts, batch sizes, p95/p99 latency, and response bytes; fix any N+1 issues found.
4. Send invalid inputs, unauthorized users, overly deep/wide queries, dependency timeouts, and retried mutations. Record the corresponding GraphQL responses, server logs, and metrics.
5. Inspect traces to confirm you can separate resolver, database, and downstream dependency time.
6. Rehearse a new version rollout, health checks, graceful shutdown, and rollback in staging.
7. Fill out the readiness sign-off template; every `FAIL` or `TODO` item must have an owner and follow-up action.

## 19. Quick Pre-Release Checklist

- [ ] Schema is compatible and all resolvers are loaded cleanly.
- [ ] HTTPS, authentication, field authorization, and tenant isolation are active.
- [ ] Input validation and error mapping do not leak internal details.
- [ ] Pagination, query depth/complexity, timeouts, and rate limits are enforced.
- [ ] N+1 is resolved; batches and DataLoaders stay within backend limits.
- [ ] Critical Queries/Mutations pass integration, security, and load tests.
- [ ] Dependency timeouts, retries, transactions, and idempotency are verified.
- [ ] Logs, metrics, traces, dashboards, and alerts are operational in staging.
- [ ] Health probes, graceful shutdown, migrations, and rollback have been tested.
- [ ] On-call engineers know the runbooks, approvers, and rollback triggers.

## 20. Completion Criteria

A Spring for GraphQL API is production-ready when its schema contract is maintainable, every read/write path protects data according to authorization rules, queries have bounded costs, resolvers and dependencies meet SLOs, errors do not leak internal information, and operations teams can detect, diagnose, mitigate, and recover from incidents. A checklist is only valuable when each conclusion is backed by evidence and an accountable owner; checking boxes without real verification does not establish readiness.
