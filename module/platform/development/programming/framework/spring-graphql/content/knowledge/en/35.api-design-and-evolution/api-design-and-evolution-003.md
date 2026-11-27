# Backward Compatibility

GraphQL APIs are typically designed to evolve continuously within a single shared schema. When the product needs new capabilities, the server can add types, fields, or arguments for newer clients to adopt, while older clients continue sending the same operations as before. This evolutionary approach only works when the server preserves **backward compatibility**: existing valid operations and the behaviors clients rely on continue working after the API changes.

In Spring for GraphQL, the SDL schema is the contract visible to clients. Resolvers, scalars, validation, authorization, and business logic determine the actual runtime behavior behind that contract. Therefore, a change might leave the SDL valid yet still break clients at runtime—for example, a field that previously always returned data starts returning `null`, an enum introduces a new value that older clients do not handle, or default pagination changes.

This lesson covers how to classify compatibility changes, how to use `@deprecated` to migrate clients gradually, how to test legacy operations with Spring for GraphQL, and how to integrate schema compatibility into your CI/CD pipeline.

## 1. What is backward compatibility?

Backward compatibility means that a newer server version continues supporting clients using the older contract throughout the API's committed support window.

For example, the initial version has this schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    name: String!
}
~~~

An older client sends:

~~~graphql
query LegacyBook($id: ID!) {
    book(id: $id) {
        id
        name
    }
}
~~~

When the product wants to rename `name` to `displayName`, the safe change is to add the new field while continuing to support the old field:

~~~graphql
type Book {
    id: ID!
    name: String! @deprecated(reason: "Use displayName instead.")
    displayName: String!
}
~~~

New clients can move to `displayName`; older clients keep querying `name` without needing an immediate release.

A compatible change must consider both the schema contract and runtime behavior. If a query still validates but the server returns data with a different meaning, clients can still break.

## 2. Four compatibility layers of a GraphQL API

| Layer | Question to answer | Examples of risky changes |
| --- | --- | --- |
| Schema compatibility | Do existing operations still validate? | Removing a field, renaming an argument, changing a type |
| Data compatibility | Do clients still receive the promised data shape and values? | A `String!` field starts returning null, changing enum meaning |
| Behavioral compatibility | Does the same operation still produce the same results and business effects? | Changing default sort, pagination, or mutation side effects |
| Operational compatibility | Are existing clients still authenticated, authorized, and served under supported conditions? | Tightening authorization, dropping client credentials, lowering rate limits |

The GraphQL specification treats a change that turns a previously valid request into an invalid one as a breaking change. However, that definition does not cover all runtime or client code generation risks. Therefore, your API workflow should distinguish:

- **Breaking change:** older operations are no longer valid or cannot be used under the old contract.
- **Dangerous change:** operations remain valid, but may cause some clients to fail at runtime.
- **Safe additive change:** extends the schema while older clients continue working without changes.

Never rely solely on a schema diff to conclude that a change is completely safe.

## 3. GraphQL usually evolves the schema instead of versioning every change

REST APIs often use URLs or headers to distinguish versions. GraphQL allows clients to select the exact fields they want to read, so many changes can be rolled out by adding capabilities to the same schema.

For example:

- Adding `Book.subtitle` does not affect operations that do not select that field.
- Adding a new query `popularBooks` does not invalidate existing queries.
- Adding an optional input field can extend filtering capabilities.
- Adding a new mutation does not force older clients to call it.

Accordingly, GraphQL usually favors additive schema evolution and avoids creating `/graphql/v2` for every new field.

That does not mean GraphQL forbids versioning. Separate versions or schemas may be necessary when business changes cannot coexist, when legal requirements differ, or when two client groups need independent contracts. Use versioning when product boundaries truly diverge, not as a substitute for a deprecation process.

## 4. Changes that are usually compatible

The following changes are generally safe for existing operations provided they do not alter the behavior of existing fields:

| Change | Why it is usually safe | Conditions to verify |
| --- | --- | --- |
| Adding a field to an object type | Clients only receive selected fields | New resolver does not alter old fields or shared resources |
| Adding a new query/mutation | Existing operations do not reference the new field | Does not change semantics of existing root fields |
| Adding an optional argument | Older clients do not need to pass the argument | Default and omitted-argument behavior must be defined |
| Adding an optional input field | Older clients can still send the old input object | Does not alter validation/defaults of existing fields |
| Adding an unreferenced type | Current operations do not use that type | Verify composition if using Federation |
| Adding SDL descriptions | Does not change types or runtime behavior | Descriptions must accurately reflect the contract |

Example of adding a field:

~~~graphql
type Book {
    id: ID!
    title: String!
    subtitle: String
}
~~~

Existing operations only select `id` and `title`, so they remain valid and do not need to change how they read data.

Even so, an additive change can still affect clients that rely on code generation, exhaustive enum/union handling, or schema snapshots. Verify against actual client groups rather than assuming every addition is harmless.

## 5. Changes that can break clients

The changes below should be treated as breaking or dangerous until proven otherwise:

| Change | Risk |
| --- | --- |
| Removing or renaming a field/type | Operations referencing the old name fail validation |
| Removing or renaming an argument | Operations passing the old argument become invalid |
| Adding a required argument without a default | Existing operations omitting the argument fail validation |
| Removing an input field | Clients sending that input field fail validation |
| Removing an enum value | Operations using that value may become invalid |
| Changing a scalar/object/list type | Clients receive a different shape or data type |
| Changing nullability | Clients may receive unexpected nulls or null propagation errors |
| Changing argument/input defaults | Operations omitting the value may experience different behavior |
| Changing field semantics | Queries still run, but clients misinterpret the data |
| Tightening authorization or validation | Previously succeeding clients may receive errors or lose access |

Some changes, such as adding an enum value or adding a member to a union, do not make existing operations invalid under GraphQL validation, but can break generated client code with exhaustive `switch` statements. Treat them as dangerous changes and evaluate how clients handle new values.

## 6. Nullability is a critical part of the contract

GraphQL uses `!` to promise a non-null value. Changing nullability can directly affect how clients handle responses and how GraphQL propagates errors.

| Before | After | Risk |
| --- | --- | --- |
| `title: String!` | `title: String` | Older clients may assume title is always present but now must handle null |
| `title: String` | `title: String!` | Stronger server guarantee, but if the resolver still returns null, the error propagates to the parent |
| `books: [Book!]!` | `books: [Book]` | Clients must handle a null list and null items |
| `books: [Book]` | `books: [Book!]!` | Data contract changes; resolvers and stored data must satisfy the new promise |

Do not change nullability just to make the SDL look "stricter." Inspect real data, downstream errors, caches, and all clients consuming the field.

If you need a field with a different nullability promise, the safer approach is usually to add a new field with the new contract, keep the old field for current clients, and deprecate the old field after migration completes.

## 7. Enums and unions require attention to exhaustive client handling

Output enums can be generated into Java, Kotlin, TypeScript, or Swift enums in clients. Some clients handle all known values with a `switch` without a fallback branch.

Example:

~~~graphql
enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

type Book {
    status: BookStatus!
}
~~~

Adding `SCHEDULED` is an additive change to the schema, but older clients may not recognize this value:

~~~graphql
enum BookStatus {
    DRAFT
    SCHEDULED
    PUBLISHED
    ARCHIVED
}
~~~

Before adding an output enum value, verify that clients have an `unknown`/fallback branch or can be updated in sync.

Similarly, adding an object type to a union can require clients to handle a new branch:

~~~graphql
union SearchResult = Book | Author | Publisher
~~~

If `Magazine` is added, clients using inline fragments and `__typename` need a strategy for unknown members. Never remove enum values or union members that clients are actively sending or reading.

## 8. Arguments, input objects, and default values

Changes in input positions can invalidate existing operations or alter behavior.

Initial example:

~~~graphql
type Query {
    books(first: Int = 20, after: String): [Book!]!
}
~~~

If `first` is changed to required without a default:

~~~graphql
type Query {
    books(first: Int!, after: String): [Book!]!
}
~~~

Existing operations calling `books` without passing `first` will fail validation.

Similarly, removing an input field, renaming an argument, or changing an enum value used as input can break published operations.

Default values are also part of the contract. When clients omit `first`, changing the default from 20 to 100 can produce larger responses and increase server load. If the default sort changes from `NEWEST` to `POPULAR`, clients still validate, but the returned data changes.

When changing defaults, check both behavior and resource limits, not just the schema diff.

## 9. Schema changes are not the only source of breaking changes

Clients often depend on semantics that SDL cannot fully describe. For example, a `price: Money!` field keeps the exact same type while changing from pre-tax price to tax-inclusive price.

Runtime changes that can break clients include:

- Changing currency units, timezones, rounding, or value interpretation rules.
- Changing the default ordering of lists or pagination cursors.
- Changing how `totalCount`, statuses, or business states are calculated.
- Changing validation rules, error codes, or whether partial data is returned.
- Changing authorization so previously valid users/tenants lose access.
- Changing mutation side effects or idempotency behavior.
- Changing the frequency, ordering, or payload of subscription events.

Document important semantics in SDL descriptions and API docs. For business-logic changes, write contract tests and changelog notes even when the schema diff reports no breaking changes.

## 10. Using @deprecated to give advance notice of changes

The `@deprecated` directive marks a field or enum value as no longer recommended for use. The old element stays in the schema and continues working while clients migrate.

Example:

~~~graphql
type Book {
    id: ID!
    name: String! @deprecated(reason: "Use displayName instead.")
    displayName: String!
}

enum BookStatus {
    PUBLISHED
    OUT_OF_PRINT @deprecated(reason: "Use ARCHIVED instead.")
    ARCHIVED
}
~~~

GraphQL introspection exposes `isDeprecated` and `deprecationReason` so tools can display warnings to developers.

A good deprecation reason should clearly state:

- Which element replaces it.
- What usage pattern clients should switch to.
- Whether there are semantic or data differences.
- Which migration documentation to read.

Do not deprecate a field merely because you want to rename it before a working replacement field is available.

## 11. Workflow for renaming a field without breaking older clients

Suppose the API currently has `Book.name` and wants to move to `Book.displayName`.

**Step 1: Add the new field and keep the old field.**

~~~graphql
type Book {
    id: ID!
    name: String! @deprecated(reason: "Use displayName instead.")
    displayName: String!
}
~~~

**Step 2: Back both fields with the same data source.**

~~~java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "name")
    public String legacyName(Book book) {
        return book.displayName();
    }

    @SchemaMapping(typeName = "Book", field = "displayName")
    public String displayName(Book book) {
        return book.displayName();
    }
}
~~~

Both fields share the same semantics, so older and newer clients receive the same value. If the old and new fields have different semantics, document the differences and do not mechanically share the same resolver.

**Step 3: Migrate clients to the new field.**

New clients select `displayName`; older clients continue selecting `name`.

**Step 4: Monitor usage of the old field.**

Identify which operations/clients still select `Book.name`, then reach out to or guide the client teams that need to migrate.

**Step 5: Remove the old field only when end-of-support conditions are met.**

Do not remove it just because the new field has shipped. Check usage, still-supported client versions, and the published deprecation schedule.

## 12. Replacing an old query or mutation with a new field

When you want to replace a root field, keep the old field intact and create a new field with a clearer name or input contract.

~~~graphql
type Query {
    searchBooks(query: String!): [Book!]!
        @deprecated(reason: "Use findBooks(text:) instead.")

    findBooks(text: String!): [Book!]!
}
~~~

Both resolvers can call a shared service:

~~~java
import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookSearchController {

    private final BookSearchService searchService;

    public BookSearchController(BookSearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    public List<Book> searchBooks(@Argument String query) {
        return searchService.search(query);
    }

    @QueryMapping
    public List<Book> findBooks(@Argument String text) {
        return searchService.search(text);
    }
}
~~~

This avoids renaming arguments in place. Existing operations stay valid, while new operations get the updated contract.

For mutations, preserve side-effect semantics. When introducing a new mutation, ensure that calling the old and new mutations does not accidentally create divergent processing paths or duplicate data.

## 13. Deprecating arguments and input fields

Some versions of the GraphQL specification support `@deprecated` on arguments and input fields, though tooling and GraphQL Java support depend on the baseline in use. Verify the GraphQL Java version managed by Spring for GraphQL before relying on deprecation introspection in those positions.

Even when the directive is supported, deprecating an argument does not solve contract changes if older clients must still pass that argument. Keep the old argument active during the migration window while providing the new path.

For example, if you need to change how search works, adding a new field is often easier to manage:

~~~graphql
type Query {
    searchBooks(query: String!): [Book!]!
        @deprecated(reason: "Use findBooks(text:) instead.")
    findBooks(text: String!): [Book!]!
}
~~~

Do not change `query: String!` to `text: String!` in place on the old field; operations passing `query` will become invalid.

## 14. Tracking usage before removing deprecated elements

Schema introspection tells you that a field is deprecated, not which clients are still using it. To decide when removal is safe, the server needs telemetry on actual operations.

At minimum, track:

- Operation name or persisted operation ID.
- Client name and client version if available.
- Selected type and field paths.
- Call counts over a sufficiently long observation window.
- Error rates and impact on specific client groups.

Do not log raw variables or personal data solely to measure field usage. Collect only the metadata needed and follow your system's privacy policies.

If the API serves mobile clients, account for older app versions still installed on devices that do not update frequently. Zero usage over a single week does not necessarily prove all clients have migrated.

## 15. Inspecting deprecations with GraphQL introspection

Client tools can query the schema to discover deprecated fields:

~~~graphql
query InspectBookDeprecations {
    __type(name: "Book") {
        fields(includeDeprecated: true) {
            name
            isDeprecated
            deprecationReason
        }
    }
}
~~~

The response confirms that `name` still exists with a clear reason, while `displayName` is the new field.

Enum values can be checked similarly:

~~~graphql
query InspectBookStatus {
    __type(name: "BookStatus") {
        enumValues(includeDeprecated: true) {
            name
            isDeprecated
            deprecationReason
        }
    }
}
~~~

Introspection only checks schema metadata. It does not prove that the old resolver still works properly or that clients have stopped using the field. Combine introspection, integration tests, and usage telemetry.

## 16. Contract testing legacy operations with GraphQlTester

A direct way to protect backward compatibility is to store key client operations as fixtures or test documents. After every schema or resolver change, re-run those operations.

Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@SpringBootTest
class BackwardCompatibilityTests {

    private final GraphQlTester graphQlTester;

    @Autowired
    BackwardCompatibilityTests(GraphQlTester graphQlTester) {
        this.graphQlTester = graphQlTester;
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

The example assumes the test configuration already provides a `GraphQlTester` wired to the application. This test verifies that the legacy operation still validates, the resolver still executes, and the old field returns the expected data.

Keep expected results meaningful to the domain. Checking only that the response has no errors is insufficient if the field's semantics could have shifted.

## 17. Testing both new clients and deprecation metadata

After adding a replacement field, verify the new path as well:

~~~java
@Test
void newBookOperationReturnsDisplayName() {
    graphQlTester.document("""
            query NewBook($id: ID!) {
                book(id: $id) {
                    id
                    displayName
                }
            }
            """)
            .variable("id", "book-42")
            .execute()
            .errors()
            .verify()
            .path("book.displayName")
            .entity(String.class)
            .isEqualTo("Clean Code");
}
~~~

You can test introspection to ensure the old field remains marked deprecated:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

record BookFieldMetadata(
        String name,
        boolean isDeprecated,
        String deprecationReason) {
}

@Test
void legacyNameFieldIsDeprecated() {
    graphQlTester.document("""
            query {
                __type(name: "Book") {
                    fields(includeDeprecated: true) {
                        name
                        isDeprecated
                        deprecationReason
                    }
                }
            }
            """)
            .execute()
            .path("__type.fields")
            .entityList(BookFieldMetadata.class)
            .satisfies(fields -> {
                BookFieldMetadata legacyName = fields.stream()
                        .filter(field -> field.name().equals("name"))
                        .findFirst()
                        .orElseThrow();

                assertThat(legacyName.isDeprecated()).isTrue();
                assertThat(legacyName.deprecationReason())
                        .isEqualTo("Use displayName instead.");
            });
}
~~~

`BookFieldMetadata` is a test DTO matching the `name`, `isDeprecated`, and `deprecationReason` fields. You can use a different projection depending on the deserialization approach used in your test suite.

## 18. Integrating schema compatibility into CI/CD

Contract tests in a single repository only check operations stored by that team. When multiple independent clients exist, add schema diff checks and operation usage checks.

A typical pipeline includes:

1. Validate SDL and build the schema.
2. Compare the new schema against the published schema.
3. Classify breaking and dangerous changes.
4. Validate registered operations or operations collected from clients.
5. Run contract/integration tests for critical clients.
6. Verify Federation composition if the schema belongs to a subgraph.
7. Publish the schema only after mandatory checks pass.

Apollo GraphOS Schema Checks is one example: build checks verify that the subgraph composes cleanly, and operations checks compare changes against operation telemetry to identify potentially affected clients. Other tools can compare SDL snapshots and validate operation registries in a similar way.

Schema checks only see operations collected within the configured data scope and time window. Rarely executed operations, offline legacy clients, or clients that do not send metadata might not show up. A passing check therefore does not replace client support policies and contract tests.

## 19. Backward compatibility in Federation

With Spring for GraphQL Federation, a subgraph schema change can affect two scopes:

- Clients calling the supergraph and relying on existing operations.
- Other subgraphs relying on entity keys, field ownership, or fields exposed through composition.

Before removing or modifying a field in a subgraph:

- Check whether another subgraph uses the field via `@key`, `@requires`, or `@provides`.
- Check whether the change breaks supergraph composition.
- Test client operations through the router, not only operations sent directly to the subgraph.
- Keep entity keys and field contracts stable during the migration window.
- Run composition checks and operation checks before publishing.

A change can be valid in an isolated subgraph SDL yet fail to compose with the remaining subgraphs. Federation therefore requires both schema compatibility and composition compatibility.

## 20. Safe deprecation and removal workflow

A workflow applicable to deprecated fields, arguments, enum values, or mutations:

**Phase 1 — Preparation**

- Identify the element to replace and the reason.
- Design the new contract, ensuring it satisfies client needs.
- Add resolvers and tests for the new contract.

**Phase 2 — Parallel release**

- Deploy the server with both old and new elements.
- Mark the old element with `@deprecated` and a specific reason.
- Update documentation, changelogs, and migration guides.

**Phase 3 — Migration**

- Notify clients currently using the old element.
- Transition clients to the new contract.
- Monitor field usage, operation usage, and post-migration errors.
- Keep the legacy path working throughout the committed support window.

**Phase 4 — Removal verification**

- Usage has dropped to 0 or only outside-of-support clients remain.
- Critical clients have confirmed migration.
- Schema checks and contract tests detect no remaining dependencies.
- Release notes and an appropriate rollback plan are ready.

**Phase 5 — Removing the old element**

- Remove the deprecated field or type in an announced release.
- Run schema diffs, operation checks, and integration tests.
- Monitor validation errors and client feedback after release.

Do not set a fixed deprecation duration across every API. Timelines should reflect client update velocity, support commitments, and impact scope.

## 21. Common pitfalls in managing backward compatibility

| Symptom | Cause | How to address |
| --- | --- | --- |
| Older clients fail after a field rename | Renamed directly in SDL | Add a new field, keep the old field and deprecate it |
| Existing queries fail validation | Removed an argument or added a required argument | Keep the old contract; add a new query/mutation if needed |
| Clients crash when a new enum value appears | Exhaustive enum handling on the client | Add a fallback branch or coordinate client updates |
| Unexpected nulls appear in responses | Changed nullability or resolver data | Keep old nullability, verify data, and add a new field if needed |
| Queries run, but results change meaning | Changed semantics without changing the schema | Treat semantics as part of the contract; add a new field or explicit migration |
| Deprecated field removed too soon | Relied only on the release date of the new field | Monitor usage and client versions before removal |
| Schema check passes, but production clients fail | Operation telemetry did not cover that client | Combine registries, contract tests, and client inventories |
| Subgraph builds, but supergraph fails | Skipped Federation composition checks | Run composition checks before publishing |
| Metrics/logs cannot identify who still uses the old field | Lacks client identity or field usage tracking | Collect appropriate client metadata and field paths |
| Deprecation reason does not aid migration | Only says "deprecated" | Specify replacement field, reason, and guidance |

## 22. Checklist for evaluating an API change

Before merging a schema change, answer each question in turn:

1. Which operations use the field, type, argument, or enum value being modified?
2. Does the change invalidate any existing operations?
3. Does the change alter nullability, response shape, or enum values?
4. Do default values, sorting, pagination, or mutation side effects change?
5. Could client code generation be broken by new enum or union members?
6. Can you add a new field/type and maintain the old contract in parallel?
7. If deprecating, are the reason and replacement clear?
8. Are there tests for legacy operations, new operations, and critical behavior?
9. Have schema diff and operation usage checks been run?
10. If using Federation, have composition and client operations through the router been verified?
11. Is there telemetry showing which clients still use the old element?
12. Have removal criteria and timing been communicated?

If you cannot answer the usage question, never conclude a change is safe merely because the server builds cleanly.

## 23. Key takeaways

- Backward compatibility spans schema, data, runtime behavior, and operations.
- GraphQL generally evolves by adding fields/types rather than versioning every change.
- Changes that prevent existing operations from validating are breaking changes.
- Enum/union additions can be dangerous changes for clients with exhaustive handling.
- Nullability, default values, and semantics are part of the contract.
- `@deprecated` helps clients discover obsolete elements, but does not track usage on its own.
- Add the new contract while keeping the old contract working during the migration window.
- Track operation/client usage before removing deprecated elements.
- Use `GraphQlTester` to keep legacy operations covered in contract tests.
- Integrate schema diffs, operation checks, and Federation composition into CI/CD.
- Remove legacy elements only after support commitments and migration conditions are satisfied.

Backward compatibility is not just keeping the schema compiling. It is a commitment that supported clients have enough time and clarity to transition without disruption. Additive design, planned deprecations, usage tracking, and testing against real operations allow a Spring for GraphQL API to evolve while remaining reliable for existing clients.

## References

- [GraphQL — Schema Design and Versioning](https://www.graphql.org/learn/schema-design/)
- [GraphQL — Schema Change Management](https://www.graphql.org/learn/governance-versioning/)
- [GraphQL — Schema Review and Breaking Changes](https://www.graphql.org/learn/schema-review/)
- [GraphQL Specification — Type System Evolution and Deprecation](https://spec.graphql.org/September2026/)
- [Apollo GraphQL — Schema Checks](https://www.apollographql.com/docs/graphos/platform/schema-management/checks)
- [Apollo GraphQL — Schema Change Management](https://www.apollographql.com/docs/graphos/platform/production-readiness/change-management)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
