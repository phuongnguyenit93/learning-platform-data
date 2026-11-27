# Pre-release compatibility checks

A GraphQL change should only be released when the new server still satisfies the operations and behaviors that supported clients depend on. Having the SDL schema build successfully is not enough to declare a release safe: existing operations may no longer validate, resolvers may return different data, authorization may change, or a subgraph may no longer compose with the rest of the supergraph.

With Spring for GraphQL, pre-release compatibility checks need to combine schema reviews, operation checks, contract tests, runtime verification, and deployment procedures. The goal is to catch breaking changes before they reach production while providing clear evidence to decide whether the release proceeds or stops.

This lesson presents a practical workflow for checking GraphQL API compatibility before release: preparing the baseline, classifying schema changes, testing legacy operations with Spring for GraphQL, checking Federation, evaluating runtime/transport, setting up CI release gates, and rolling out in stages.

## 1. What is pre-release compatibility?

Pre-release compatibility is the process of verifying that a version about to be released remains compatible with consumers and dependent systems within the supported scope.

For example, production currently has the schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    name: String!
}
~~~

A release wants to rename `name` to `displayName`. If you simply change the SDL to:

~~~graphql
type Book {
    id: ID!
    displayName: String!
}
~~~

then existing operations selecting `name` will no longer validate. The server can still build, yet legacy clients will fail immediately upon sending requests.

A compatible change should preserve the old field during the migration window:

~~~graphql
type Book {
    id: ID!
    name: String! @deprecated(reason: "Use displayName instead.")
    displayName: String!
}
~~~

Before releasing, verify that both fields have resolvers, return accurate data, and legacy clients continue running. Only after usage of `name` has been handled according to support policy should removal be considered.

## 2. Five layers to check

| Layer | What to verify | Potential failure examples |
| --- | --- | --- |
| Schema | Is the new SDL valid and does it preserve existing operations? | Removing fields, changing arguments, altering types |
| Operation | Do actively used queries/mutations/subscriptions still run? | Clients still send old arguments or select removed fields |
| Runtime contract | Do resolvers still return the right shape, nullability, and semantics? | Field changes meaning or returns unexpected nulls |
| Security and transport | Do authentication, authorization, headers, endpoints, and protocols stay compatible? | Legacy clients get 401/403 or WebSocket fails to connect |
| Dependent systems | Are databases, downstream services, DataLoaders, and Federation compatible? | Incomplete data migrations, composition failure |

These layers complement one another. Schema diffs primarily detect changes in the type system; contract tests verify operation behavior; integration tests and rollouts verify the system works in production-like environments.

## 3. Preparing a baseline before comparing

You cannot evaluate a change without knowing the current state clients are using. Before running compatibility checks, gather the baseline:

- The currently published schema or the schema currently serving production.
- The candidate schema from the commit/release about to ship.
- Registered operations or client operation telemetry.
- Client names, versions, environments, and relevant user groups.
- Persisted queries/allowlists if the API uses those mechanisms.
- List of subgraphs, routers, and dependent services.
- Contract tests, integration tests, and representative test data.

Store the released production schema as a versioned artifact or clear commit. Do not use a schema from an arbitrary branch as the baseline if it may already diverge from what is running.

If multiple environments or variants exist, identify which schema production clients are actually calling. The latest staging schema does not necessarily represent the production contract.

## 4. Collecting operations that clients actually use

SDL tells you which fields the server supports; operations tell you which fields clients are calling.

An operation registry or operation telemetry helps identify:

- Operation names and operation IDs.
- Client names/versions sending operations.
- Selected fields, arguments, and types.
- Call frequency over an observation window.
- Operations belonging to older mobile clients or low-traffic consumers.

Example operation:

~~~graphql
query BookDetails($id: ID!) {
    book(id: $id) {
        id
        name
        author {
            displayName
        }
    }
}
~~~

If a release removes `Book.name`, this operation breaks even if newer tests only query `displayName`.

Operation telemetry has blind spots: offline clients, rarely used operations, or clients omitting metadata may not appear in the dataset. Therefore, combine telemetry with your inventory of supported consumers, operation fixtures, and per-client release information.

Do not record raw variables or personal data solely to track usage. Collect only the metadata necessary to identify operations and consumers.

## 5. Classifying schema changes

Before release, review the schema diff and classify changes by impact:

| Category | Example | Initial decision |
| --- | --- | --- |
| Additive | Adding a nullable field to an object type | Usually safe to proceed after verifying the resolver |
| Breaking | Removing a field currently used by operations | Block release until migrated or granted an approved exception |
| Dangerous | Adding an output enum value, changing defaults, changing nullability | Requires checking specific consumers and runtime behavior |
| Metadata-only | Editing descriptions or adding deprecation reasons | Usually safe; still requires schema review |
| Composition change | Changing field ownership or entity keys between subgraphs | Requires composition checks and review of affected consumers |

Changes that generally require careful review:

- Removing or renaming fields, types, arguments, input fields, or enum values.
- Adding a required argument/input field without a default.
- Changing scalar, object, list, or nullability types.
- Changing argument/input defaults.
- Changing output enums or union members.
- Changing directives, entity keys, or field ownership in Federation.

An additive schema change can still be dangerous for client code generation or exhaustive enum handling. Rely on actual client behavior rather than trusting a "non-breaking" label from a schema diff alone.

## 6. Running automated schema diffs

Run a schema diff between the production schema and the candidate schema in CI. The output should display:

- Added, modified, or removed elements.
- Breaking changes.
- Dangerous changes needing further evaluation.
- Deprecated fields and their reasons.
- Affected schema coordinates, such as `Book.name` or `Query.books(first:)`.

If using Apollo GraphOS, Schema Checks can run via the Rover CLI and integrate into your pipeline. Build checks verify schema validity; with Federation, they also check whether subgraphs compose into a supergraph. Operations checks compare the candidate schema against operation history to identify impacted clients.

Operations checks rely on operation metrics reported to GraphOS. The default window is seven days and is configurable. If no metrics exist to compare against, potentially dangerous changes are flagged as failing; that reflects missing evidence, not confirmation that the schema is safe.

Example running a check for a graph:

~~~bash
rover graph check my-graph@production --schema ./schema.graphql
~~~

For a Federation subgraph:

~~~bash
rover subgraph check my-graph@production \
    --name books \
    --schema ./books/schema.graphql
~~~

Replace graph names, variants, subgraphs, and schema paths with your project's actual values. Verify your CLI version and current Rover documentation before placing commands into production pipelines.

If not using GraphOS, you can use schema snapshot/diff tools, GraphQL Java validation, or an internal operation registry. What matters is checking the same baseline and the same operation set consistently across releases.

## 7. Evaluating operation checks and dangerous changes

Operation checks answer: given the candidate schema, are recorded operations still valid and safe to execute?

Results typically distinguish **broken** operations (no longer valid against the new schema) from **potentially affected** operations (still valid yet behavior or client impact may change). Inspect each operation's details to see which field/argument is impacted and which consumer sends it.

Analyze each affected operation:

- Does the operation lose a field or argument?
- Are declared variables still compatible with updated arguments?
- Can the operation still validate while receiving new enum values or a different shape?
- Which client sends that operation?
- What is that client's call frequency and criticality?
- Is there already a newer migrated client version?

Do not ignore dangerous changes simply because operations still validate. For instance, adding `SCHEDULED` to an output enum does not fail validation on old queries, yet a client using an exhaustive `switch` may not know how to render the new value.

If checks report an operation unused during the observation window, verify support policies and client types before allowing removal. An older mobile app might generate no traffic for days while still remaining within its support window.

## 8. Preserving legacy operations with contract tests in Spring for GraphQL

Schema checks based on operation history do not replace behavioral tests. With Spring for GraphQL, `GraphQlTester` provides a unified request-testing workflow across multiple transports.

You can store legacy operations under `src/test/resources/graphql-test/` and re-run them on every schema/resolver change.

Example testing a legacy operation:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BookCompatibilityTests {

    @LocalServerPort
    private int port;

    private GraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        WebTestClient client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port + "/graphql")
                .build();
        this.graphQlTester = HttpGraphQlTester.create(client);
    }

    @Test
    void legacyBookOperationStillWorks() {
        graphQlTester.document("""
                query LegacyBook($id: ID!) {
                    book(id: $id) {
                        id
                        name
                    }
                }
                """)
                .variable("id", "book-42")
                .execute()
                .errors()
                .verify()
                .path("book.name")
                .entity(String.class)
                .isEqualTo("Clean Code");
    }
}
~~~

This example assumes the test configuration provides a `GraphQlTester` connected to the application. In integration tests, you can build `HttpGraphQlTester` from `WebTestClient` or use `WebSocketGraphQlTester`/`RSocketGraphQlTester` for the corresponding transport.

For operations saved in files, `documentName("legacyBook")` lets tests reuse documents instead of embedding query text in Java. Keep operation fixtures in version control so reviewers can see which consumer contracts a release protects.

## 9. Verifying responses, nullability, and partial errors

An operation can still validate while returning a different response than before. Contract tests should check:

- Legacy fields still have values and preserve semantics.
- New fields have expected values.
- Nullability is not violated.
- Lists do not unexpectedly contain null items or become null themselves.
- Error codes and error paths still match the contract.
- Partial data is returned in a way clients can handle.

Example testing both fields during migration:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

@Test
void legacyAndReplacementFieldsReturnSameValue() {
    graphQlTester.document("""
            query BookNames($id: ID!) {
                book(id: $id) {
                    name
                    displayName
                }
            }
            """)
            .variable("id", "book-42")
            .execute()
            .errors()
            .verify()
            .path("book")
            .entity(BookNames.class)
            .satisfies(book -> {
                assertThat(book.name()).isEqualTo("Clean Code");
                assertThat(book.displayName()).isEqualTo(book.name());
            });
}

record BookNames(String name, String displayName) {
}
~~~

This example checks that two fields share semantics. If the new field has different semantics, write separate assertions instead of forcing equality.

When testing intentional errors, use `errors().expect(...)` or `errors().satisfy(...)` to verify the error contract. Do not filter out all errors with `verify()` when the release needs to catch resolver failures.

## 10. Verifying inputs, validation, and default values

Input changes are frequently overlooked when testing only response fields.

Before releasing, verify:

- Older clients omitting optional arguments still run.
- Legacy input objects are still accepted.
- Newly added arguments do not break existing operations.
- Default pagination, sorting, and filtering did not change unintentionally.
- Validation errors retain expected codes and paths.
- Custom scalars still serialize/parse using the same formats.

For instance, if `books(first: Int = 20)` changes its default to `100`, existing operations still validate yet may fetch much more data. Test omitting `first`, measure response size, and verify server limits remain enforced.

Do not test queries only with every argument passed explicitly. Real clients commonly rely on schema default values.

## 11. Verifying authorization and security compatibility

An authorization change can reject valid clients even when the schema is unchanged.

Run contract tests across important identities:

- Anonymous clients if the API permits public access.
- Authenticated users.
- Users with lower and higher roles.
- Different tenants.
- Service accounts or client credentials.
- Legacy clients using supported headers or token formats.

Test field-level authorization, `@PreAuthorize`, `DataFetcherExceptionResolver`, error classification, and GraphQL error payloads. Verify unauthorized users cannot read data through nested fields, DataLoaders, or entity resolvers.

Do not use a single admin account for the entire test suite. Tests running solely with elevated privileges can hide authorization regressions.

## 12. Verifying mutations and side effects

Mutations are behavioral contracts: the same inputs must preserve committed meanings and effects.

Before releasing, verify:

- Legacy inputs still bind and validate.
- Mutations produce no unexpected side effects.
- Idempotency keys or retry behavior remain consistent.
- Errors do not mislead clients into thinking a mutation succeeded.
- Responses return the right object/version/state after mutation.
- Transaction rollbacks and event publications preserve expected ordering.

For example, changing `createOrder` to automatically capture payment is a major semantic change even if the schema stays identical. Legacy clients may expect orders to be created in a `pending` state.

Test mutations against a test database or appropriate test doubles, then inspect actual persisted state rather than checking only JSON responses.

## 13. Verifying subscriptions and transports

If the release modifies WebSocket or RSocket, test those transports separately:

- Endpoints and protocols remain compatible.
- Authentication headers or connection initialization payloads do not change unexpectedly.
- Legacy clients can still subscribe and receive events.
- `next`, `error`, and `complete` follow the protocol accurately.
- Reconnection and cancellation work.
- Heartbeats, timeouts, and connection limits are appropriate.
- Event payloads preserve shape and semantics.

`GraphQlTester` supports `WebSocketGraphQlTester` and `RSocketGraphQlTester`; subscription tests can use `executeSubscription()` and Reactor `StepVerifier` to assert streams.

An HTTP query test does not prove WebSocket subscriptions are compatible. Run tests over the exact transports production clients use.

## 14. Verifying custom scalars and data

Custom scalars often represent formats clients rely on directly, such as `Date`, `DateTime`, `Money`, `URL`, or `UUID`.

Before releasing, check:

- Input serialization and output serialization.
- Time zones, offsets, and precision.
- Decimal rounding, currencies, and units.
- Null and invalid value handling.
- Whether formatting changed across client versions.
- Whether JSON representation keeps the expected data type.

For instance, changing `DateTime` from ISO-8601 with offset to a local time string can cause clients to misinterpret timestamps even though the GraphQL type name remains `DateTime`.

Keep boundary values in contract fixtures: timestamps across UTC midnight, high-precision decimals, empty strings, nulls, and invalid values.

## 15. Verifying performance and query limits

A schema-compatible release can still cause operational incidents if existing queries become slower or consume more resources.

Inspect changes affecting:

- Resolvers calling additional downstream services.
- DataLoader batch sizes or cache scopes.
- Database queries and N+1 patterns.
- Pagination default/max page sizes.
- Query depth/complexity limits.
- Response size and serialization.
- Timeouts, concurrency, and rate limits.

Use representative operations from production telemetry as load-test inputs. Compare latency percentiles, error rates, throughput, database calls, and memory against the pre-release baseline.

If adding a new field causes an existing resolver to fetch extra data even when clients do not select that field, review the implementation. GraphQL should resolve selected fields efficiently without incurring unexpected overhead.

## 16. Verifying Federation composition and downstream compatibility

With Spring for GraphQL Federation, checking a single subgraph in isolation is insufficient. The candidate schema must compose into the supergraph and preserve cross-subgraph dependencies.

Before releasing, verify:

- Entity `@key` fields remain stable and resolvers can resolve representations.
- Field ownership does not conflict.
- `@requires` and `@provides` still match supplied data.
- Other subgraphs no longer depend on fields about to be removed.
- Operations through the router still run after composition.
- The router can load the new supergraph schema.

Apollo GraphOS build checks verify whether a subgraph schema composes with the remaining subgraphs. Operations checks further verify whether recorded client operations are impacted.

If not using GraphOS, run composition with the Rover CLI or equivalent Federation tooling in CI. Do not wait until publishing to production to discover a schema fails to compose.

## 17. Verifying deployment configuration and infrastructure

Compatibility also depends on environment configuration and external dependencies. Compare the candidate against production across:

| Component | What to verify |
| --- | --- |
| HTTP endpoint | URL, HTTP method, content type, status codes |
| Headers | Authorization, tracing, client identity, CORS |
| WebSocket/RSocket | Protocol, endpoint, handshake, reconnect |
| GraphQL configuration | Schema locations, scalars, instrumentation, exception resolvers |
| Database | Migrations run before new code, indexes, and query plans |
| Downstream services | API contracts, timeouts, retries, credentials |
| Runtime config | Feature flags, environment variables, secrets |
| Limits | Body size, depth, complexity, pagination, rate limits |
| Observability | Logs, traces, metrics, and alerts active |

If new code depends on a newly added database column, deploy migrations using expand-contract: add the compatible structure first, deploy code using the new structure, backfill/migrate data, and only remove the old structure once every application instance has transitioned.

## 18. Setting up release gates in CI/CD

A pipeline can be structured into sequential gates:

| Gate | Task | Pass criteria |
| --- | --- | --- |
| 1. Build | Compile and build artifacts | Build succeeds |
| 2. Schema validation | Parse/validate SDL and schema wiring | No schema errors |
| 3. Schema diff | Compare against production baseline | No unresolved breaking changes |
| 4. Operation checks | Validate against operation history/registry | No impacted consumers without a plan |
| 5. Contract tests | Run legacy and new operations | Responses/errors/semantics pass |
| 6. Security tests | Roles, tenants, and authentication | No access-control regressions |
| 7. Federation checks | Compose subgraphs and test through router | Composition and operation checks pass |
| 8. Integration/performance | Downstream, migrations, load tests | Within SLO thresholds |
| 9. Release approval | Review evidence and rollout plan | Explicit GO decision |

Do not treat all warnings as passes. Every dangerous change needs an owner, listed affected consumers, and documented risk acceptance.

With GraphOS, run separate schema checks for each protected variant, such as `staging` and `production`. Rover commands in CI should authenticate using an `APOLLO_KEY` secret stored in CI's secret store; never run interactive login steps in pipelines.

Conceptual pipeline step example:

~~~yaml
steps:
  - name: build-and-unit-tests
    run: ./gradlew test

  - name: schema-compatibility
    run: rover graph check my-graph@production --schema ./schema.graphql

  - name: contract-tests
    run: ./gradlew test --tests '*Compatibility*'

  - name: build-artifact
    run: ./gradlew bootJar
~~~

This is an illustrative example. Adjust Gradle tasks, graph references, and commands to fit your build system and environment. For Federation, replace `graph check` with the appropriate `subgraph check`.

## 19. Staged rollouts and safe ordering

For additive changes, rollouts are generally safer when following an expand pattern:

1. Add new fields/types and resolvers on the server.
2. Deploy the new server and wait until all replicas are ready.
3. Publish the candidate schema after the implementation is live.
4. Update clients to start using the new fields.
5. Monitor errors, latency, and operation usage.
6. After the migration window, deprecate and schedule removal of old fields.

For Federation, Apollo recommends running schema checks first, deploying the subgraph to infrastructure, waiting for replicas to roll out, and only then publishing the corresponding schema. This prevents the router from receiving a schema with new fields while some replicas still lack resolvers to serve them.

If a release includes incompatible changes, create a dedicated migration plan, notify consumers, and potentially release in multiple phases. Do not publish a breaking schema simply because new server code has been deployed.

## 20. Rollback and forward recovery

Rolling back an application does not automatically mean rolling back the schema immediately. If new clients have already started querying a newly added field, removing that field from the schema can cause additional errors.

A safer strategy:

- Keep the schema additive if application code can roll back without causing the new field to fail.
- Use feature flags to turn off new behavior while preserving the field contract.
- Decouple schema publishing from application deployment where the platform supports it.
- Prepare backward-compatible database migrations.
- Monitor failing operations and affected clients after each stage.
- When schema fixes are required, prefer compatible forward fixes.

For breaking changes, know clearly which schema the router currently publishes and which clients have switched to the new contract. Do not assume reverting a commit restores the prior state cleanly.

## 21. Release checklist and GO/NO-GO decision

Before releasing, the release owner can confirm:

- [ ] Candidate schema has been diffed against the production schema.
- [ ] All breaking changes have been removed or have approved migrations/exceptions.
- [ ] Dangerous changes have been evaluated against real clients.
- [ ] Operation history and persisted operations have been checked.
- [ ] Contract tests for both legacy and new operations pass.
- [ ] Nullability, defaults, enums, and custom scalars have been verified.
- [ ] Authentication, authorization, and tenant isolation pass.
- [ ] Mutation side effects and subscription streams are verified if changed.
- [ ] Federation composition and operation checks pass if applicable.
- [ ] Database migrations and downstream dependencies are ready.
- [ ] Performance meets SLOs and query limits do not block valid clients.
- [ ] Metrics, logs, traces, and alerts can observe the release.
- [ ] Rollout, rollback/forward recovery, and owners are clear.

**GO** when all mandatory gates pass, warnings are addressed or acceptably justified, and the rollout plan is ready to execute.

**NO-GO** when production operations break without a migration, the schema fails to compose, critical contract tests fail, access controls regress, or dependencies are unready.

If a check lacks sufficient data, record it as **UNKNOWN** and determine how to gather evidence. Never automatically promote UNKNOWN to PASS.

## 22. Common pitfalls during compatibility checks

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Schema builds, yet clients fail | Operation checks were skipped | Compare schema against operation registry/telemetry |
| Schema diff passes, yet response semantics changed | Only the type system was checked | Add runtime contract tests |
| Legacy clients go undetected | Operation telemetry coverage is incomplete | Combine client inventory and persisted operations |
| Tests only run as admin | Role/tenant authorization was not tested | Create test principals per permission group |
| HTTP tests pass, yet subscriptions fail | WebSocket/RSocket were not tested | Run tests over actual transports |
| Subgraph runs alone, yet router fails | Composition checks were skipped | Validate supergraph candidate in CI |
| New field is in schema before resolvers are ready | Schema published before all replicas deployed | Deploy and health-check subgraphs before publishing |
| Rollback breaks newer clients | Schema reverted after clients adopted new fields | Keep contracts additive and use forward recovery |
| Load tests differ from production | Synthetic queries do not represent real load | Use sanitized production operation telemetry |
| Checks pass despite missing operation data | Missing data confused with zero impact | Record UNKNOWN and expand operation coverage |

## 23. Key takeaways

- Pre-release compatibility must check schema, operations, runtime, security, transport, and dependencies.
- Always compare the candidate schema against the released production baseline.
- Schema diffs and operation checks answer two different questions.
- Use `GraphQlTester` to replay legacy operations and verify actual responses.
- Verify roles/tenants, mutations, subscriptions, and custom scalars whenever relevant changes ship.
- With Federation, run composition and operation checks across the supergraph.
- Deploy implementations before publishing schemas with new fields.
- Monitor client usage before removing deprecated elements.
- Prepare forward recovery; rolling back a schema can break newer clients.
- Every release gate needs clear evidence and an explicit GO/NO-GO/UNKNOWN status.

Pre-release compatibility checks turn a GraphQL change into an evidence-based decision. When the baseline, real operations, contract tests, Federation checks, and rollout plan are all verified together, teams can ship changes while protecting supported clients.

## References

- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Apollo GraphOS — Schema Checks](https://www.apollographql.com/docs/graphos/platform/schema-management/checks)
- [Apollo GraphOS — Run Schema Checks](https://www.apollographql.com/docs/graphos/platform/schema-management/checks/run)
- [Apollo GraphOS — Deploying API Changes](https://www.apollographql.com/docs/graphos/platform/production-readiness/change-management)
- [Apollo GraphOS — Deployment Best Practices](https://www.apollographql.com/docs/graphos/platform/production-readiness/deployment-best-practices)
- [Apollo Federation — Schema Composition](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/composition)
