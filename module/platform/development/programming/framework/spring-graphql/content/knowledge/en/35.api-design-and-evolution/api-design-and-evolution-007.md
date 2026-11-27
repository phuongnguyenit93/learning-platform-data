# Versioning via Schema Evolution

GraphQL APIs typically use a single continuously evolving schema rather than creating separate endpoints for each version. When the contract changes additively, older clients keep querying the fields they already know, while newer clients can select new fields. This approach lets the API grow without forcing all clients to upgrade at once.

However, schema evolution is only safe when you understand the impact of each change on queries, mutations, inputs, outputs, and generated client code. Removing a field, adding a required argument, changing nullability, or modifying enum value sets can cause active clients to hit validation errors or data-processing failures.

In Spring for GraphQL, the SDL schema is the public contract, while controllers and application services implement the behavior behind that contract. This lesson covers how to evolve schemas, mark legacy fields with `@deprecated`, execute transition periods, recognize breaking changes, and structure release workflows.

## 1. How does GraphQL versioning differ from REST versioning?

In REST, many systems maintain endpoints such as `/api/v1/books` and `/api/v2/books`. GraphQL typically keeps a single stable endpoint, such as `/graphql`, while expanding the schema over time.

Clients only request fields included in their selection set. Thus, when the server adds a new field to type `Book`, older queries do not automatically receive that field and legacy responses preserve the exact shape the client requested.

For example, the initial schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
~~~

Later the server adds `publishedAt`:

~~~graphql
type Book {
    id: ID!
    title: String!
    publishedAt: String
}
~~~

Older clients can still send:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
    }
}
~~~

Newer clients can select the additional field:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
        publishedAt
    }
}
~~~

Both clients can operate against the same schema. This is the primary advantage of schema evolution: changes are adopted according to client needs rather than requiring coordinated endpoint version switches.

GraphQL does not prohibit maintaining multiple schema versions. When a change cannot be made compatible, a system can still expose a separate endpoint or schema during a transition period. However, treat that as an option for genuinely major changes, because every schema must be maintained, tested, and operated.

## 2. Additive change principles

An additive change expands the capabilities of the schema without invalidating previously valid queries.

Changes that are generally safe:

- Adding a new field to an object type or query root.
- Adding a new optional argument or one with an appropriate default value.
- Adding an optional input field to an input object.
- Adding a new mutation while keeping the old mutation.
- Adding a new type without altering the meaning of existing types.

For example, adding optional filters:

~~~graphql
type Query {
    books(
        term: String!
        category: String
        limit: Int = 20
    ): [Book!]!
}
~~~

Older clients passing only `term` remain valid. Newer clients can also pass `category` and `limit`.

For input objects:

~~~graphql
type Query {
    books(input: BookSearchInput!): [Book!]!
}

input BookSearchInput {
    term: String!
    category: String
    publishedAfter: String
}
~~~

Older clients sending only `term` remain valid because the two new fields can be absent. Resolvers need clear definitions for when a field is omitted, sent as `null`, or given a concrete value if the contract must distinguish those three states.

Not every change that looks additive is safe. Adding a required argument, adding a non-null input field without a default, or adding an output enum value that clients handle with an exhaustive `switch` can break existing clients. Evaluate both the schema and how clients generate and handle code.

## 3. Identifying breaking changes

A breaking change makes existing queries invalid or prevents older clients from properly handling responses and API behavior.

| Change | Client impact | Assessment |
| --- | --- | --- |
| Adding a new output field | Older clients do not select it, so responses stay unchanged | Usually safe |
| Adding an optional argument | Existing queries can still call the field | Usually safe |
| Adding a required argument | Existing queries omit the argument and become invalid | Breaking |
| Adding an optional input field | Existing inputs stay valid | Usually safe |
| Adding a non-null input field without a default | Existing inputs omit a required field | Breaking |
| Removing an active field or argument | Existing queries become invalid | Breaking |
| Removing an enum value sent by clients | Existing mutations/queries may become invalid | Breaking |
| Changing a scalar or return type | Clients may fail to parse or deserialize | Potentially breaking |
| Changing a nullable field to non-null | Alters nullability contract and generated types | Requires client review |
| Changing a non-null field to nullable | Clients must handle possible `null` values | Potentially breaking |
| Changing a default value | Queries omitting the argument may see altered behavior | Potentially breaking |
| Adding a union member | Clients with exhaustive handling may not recognize the new member | Potentially breaking |
| Changing a field's business meaning | Queries validate, but returned results change | Behavioral breaking change |

Nullability is a critical part of the contract. `Book` and `Book!` do not mean the same thing: a nullable field may return `null`, whereas a non-null field guarantees a value or bubbles an error up to its parent under GraphQL rules. Changing `!` must be evaluated against client codegen, null-handling logic, and actual data semantics.

Adding values to output enums also requires caution. Existing GraphQL queries may still validate, but clients generating closed enum types or using exhaustive `switch` statements can fail when the server returns the new value. Conversely, adding enum values used only in inputs usually does not affect older clients unless they send the new value. Evaluate input enums and output enums separately.

Outside the schema, changing authorization rules, default sorting, pagination behavior, currency unit meanings, or filter rules can also break clients even if schema diffs detect nothing. The contract encompasses semantics, not just SDL.

## 4. Deprecate fields before removing them

Do not remove an old field immediately when a new field name is introduced. GraphQL supports the `@deprecated` directive to mark fields or enum values as no longer recommended for use.

Example renaming `Query.book` to `Query.bookById`:

~~~graphql
type Query {
    book(id: ID!): Book
        @deprecated(reason: "Use bookById instead.")

    bookById(id: ID!): Book
}
~~~

Both fields share the same return type and meaning. The old field stays functional during the transition window. Newer clients use `bookById`; older clients continue using `book`.

The `@deprecated` directive can be read via introspection. Tooling, IDEs, and schema-generated docs can surface the old field alongside its deprecation reason. However, the directive does not block requests or automatically migrate clients to the new field. Migration still requires coordination between the server team and client owners.

Write short, specific, actionable reasons. For APIs with multiple clients, the reason can point to the replacement field, migration documentation, or target end-of-support milestone.

Do not use deprecation on a field that remains the official choice with no replacement planned. Deprecation is an API lifecycle signal, so it requires monitoring and a clear removal policy.

## 5. Implementing old and new fields in Spring for GraphQL

The SDL schema declares both fields during the transition window. Controllers can map both fields to the same application service to preserve consistent behavior.

~~~java
package com.example.books.graphql;

import com.example.books.application.Book;
import com.example.books.application.BookNotFoundException;
import com.example.books.application.BookService;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
    }

    @QueryMapping(name = "bookById")
    public Book findBookById(@Argument String id) {
        return bookService.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

Both resolvers call the same service method. Consequently, access control, lookup behavior, not-found handling, and business rules are not duplicated into two independent implementations.

During the transition window, you can add logging or dedicated metrics for the legacy field to identify which clients still use it. Avoid logging full query variables or sensitive data solely to measure usage. Attach client identification using verified authentication context or trusted metadata if supported by the system.

When the new field also changes semantics, do not simply rename the resolver and share the implementation mechanically. Explicitly define the business differences and write contract tests for both fields.

## 6. The expand, migrate, contract workflow

A controlled rollout divides changes into three stages.

~~~mermaid
flowchart TD
    A[Current schema and clients] --> B[EXPAND]
    B --> C[Add new field or input]
    C --> D[Deploy server supporting old and new]
    D --> E[MIGRATE]
    E --> F[Move clients to new contract]
    F --> G[Measure old field usage]
    G --> H{Old usage is zero for agreed window?}
    H -- No --> E
    H -- Yes --> I[CONTRACT]
    I --> J[Remove deprecated field]
    J --> K[Publish updated schema]
~~~

**Expand — extend the schema**

- Add the new field, optional argument, or input field.
- Implement the resolver and test the new contract.
- Keep the old field so existing queries continue working.
- Document the updated schema and publish usage examples.

**Migrate — transition clients**

- Update each client to use the new field.
- Check codegen and persisted operations.
- Track usage of the old field by client and operation.
- Confirm that supported application versions have transitioned.

**Contract — narrow the schema**

- Remove the old field only after usage has dropped to zero for the agreed observation period.
- Account for low-frequency clients, older mobile apps, scheduled jobs, and partner integrations.
- Announce the end-of-support date prior to deployment.
- Run schema diffs and contract tests after removal.

Do not treat a few days without traffic as proof that a field is no longer used. A client might run monthly, quarterly, or only in emergency scenarios. The waiting window must align with real client lifecycles.

## 7. Tracking usage and deciding when to remove

A schema shows which fields are deprecated, but cannot tell you who is still calling them. Runtime observability is required.

Useful data includes:

- Operation name and operation type (`query`, `mutation`, `subscription`).
- Field name or field coordinate being executed.
- Client/application ID from a trusted authenticated source.
- Success counts, error counts, and last-seen timestamp.
- Application version if clients send authenticated or controlled metadata.

You can use GraphQL instrumentation, observation, structured logs, or persisted operation registries to gather data. Avoid storing raw queries, arguments, or responses unnecessarily as they may contain sensitive data.

A field should only be removed with sufficient evidence:

1. Published clients are using the replacement field.
2. No traffic hits the old field over a window covering operational schedules.
3. Persisted operations and batch jobs have been updated.
4. External integration owners have been notified.
5. A rollback or schema restoration plan is ready if a missed client is uncovered.

If you cannot identify which clients call the legacy field, exercise extra caution. Keep the deprecated field longer or issue advance warnings before removal.

## 8. Designing input and mutation changes

Mutations often receive inputs from many clients. When extending an input object, favor optional fields and clearly define default behavior.

Old input example:

~~~graphql
input CreateBookInput {
    title: String!
    authorId: ID!
}
~~~

You can add an optional field:

~~~graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    language: String
}
~~~

Older clients continue sending the original two fields. Newer clients can send `language`. The application service must define the default value when `language` is omitted.

Avoid adding a required non-null field to an input object already used by multiple clients:

~~~graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    language: String!
}
~~~

After this change, older inputs lacking `language` become invalid. If new mandatory data is required, consider adding a nullable field first, applying a default, or creating a new mutation with the new contract during migration.

Do not rename an input field by removing the old name immediately. If your schema and GraphQL Java version support deprecation on input values, you can mark the legacy input field or argument; otherwise, keep both fields during a transition period with clear precedence rules in the application layer. Avoid situations where clients send conflicting values without deterministic server resolution.

## 9. Enums, interfaces, and unions require specific policies

Composite types and enums can cause breaking changes even when query documents still validate.

**Enum**

~~~graphql
enum BookFormat {
    PRINT
    EBOOK
    AUDIOBOOK
}
~~~

If the server adds `PODCAST` to a returned enum, clients with enums generated from the older schema may not know how to handle that value. Clients should have a fallback branch for unrecognized values, or the server needs a separate versioning plan if clients cannot be extended.

If an enum value is no longer used, mark it deprecated first:

~~~graphql
enum BookFormat {
    PRINT
    EBOOK
    AUDIOBOOK @deprecated(reason: "Use DIGITAL instead.")
    DIGITAL
}
~~~

**Interface**

Adding a field to an interface expands the contract that implementing types must satisfy. Related resolvers and object types must be updated. Modifying or removing an existing field can break queries selecting that field on the interface.

**Union**

Adding a member to a union can impact clients using inline fragments and exhaustive handling by `__typename`. Clients should include a branch for unknown types to tolerate schema evolution gracefully.

~~~graphql
union SearchResult = Book | Author | Publisher
~~~

When `Publisher` is added, older clients may still validate the query, but result-handling code needs a fallback for a new `__typename`. Do not assess compatibility solely on whether a GraphQL document passes validation.

## 10. Managing schema contracts in CI/CD

SDL schemas should be managed as API contracts with code review and change history. Every pull request modifying the schema should check client impact.

A CI pipeline can include:

1. Build or extract the new SDL schema from source.
2. Compare it against the currently released schema.
3. Classify changes as additive, deprecated, dangerous, or breaking per organizational policy.
4. Require additional review if breaking changes are present.
5. Run contract tests for critical operations.
6. Publish the updated schema alongside migration notes at release time.

Automated schema diffs help catch field deletions, type changes, new required arguments, or enum modifications. However, diff tools cannot understand every semantic, authorization, or business-rule change. API reviews must still evaluate behavioral impact.

With persisted queries or an operation registry, validate the set of active client queries against the new schema. Removing a field can immediately cause stored operations to fail validation as soon as clients resend them.

## 11. Testing compatibility

Test both old and new contracts during migration. For example, use `ExecutionGraphQlServiceTester` to build a `GraphQlTester` executing directly against Spring's `ExecutionGraphQlService` without spinning up an HTTP client:

~~~java
package com.example.books.graphql;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;

@SpringBootTest
class BookSchemaEvolutionTests {

    @Autowired
    ExecutionGraphQlService graphQlService;

    @Test
    void oldAndNewQueryFieldsReturnTheSameBook() {
        GraphQlTester graphQlTester =
            ExecutionGraphQlServiceTester.create(graphQlService);

        String oldId = graphQlTester.document("""
                query {
                    book(id: "book-42") {
                        id
                        title
                    }
                }
                """)
            .execute()
            .path("book.id")
            .entity(String.class)
            .get();

        String newId = graphQlTester.document("""
                query {
                    bookById(id: "book-42") {
                        id
                        title
                    }
                }
                """)
            .execute()
            .path("bookById.id")
            .entity(String.class)
            .get();

        assertThat(oldId).isEqualTo(newId);
    }
}
~~~

This example assumes fixture `book-42` is loaded and the service returns the same record for both resolvers. The test proves that the behavior of the old and new fields remains consistent during migration.

Additionally, include tests for:

- Old queries still validating and executing after adding new fields.
- Clients being able to use the new fields.
- Old inputs remaining valid when only optional fields are added.
- Deprecated fields continuing to function before removal.
- Old queries failing cleanly once a field is removed in a new schema version.
- Enum/union clients handling fallbacks for unknown values or types.
- Authorization and nullability upholding the contract.

For critical clients, store representative operations as consumer contract tests. When changing the schema, re-run all of these operations to catch validation failures before deployment.

## 12. When is a separate schema version needed?

Some changes cannot be rolled out through additive evolution—such as changing a field's core meaning, altering the foundational data model, or shifting semantics so older clients can no longer operate.

In such cases, you can maintain two schemas for a period:

- The old endpoint/schema continues serving unmigrated clients.
- The new endpoint/schema holds the updated contract.
- Both schemas have clear end-of-support schedules and client migration plans.
- Shared business logic should live in application services to avoid forking the entire domain layer.

Do not add an argument like `version: 1` to every query or mutation. That forces clients to pick versions field by field, complicating the schema and making it difficult to compose data across fields.

Similarly, do not create a new schema version just to rename a single field. When changes can be additive, adding a new field, deprecating the old one, and migrating based on usage is far simpler.

## 13. Common mistakes when evolving a GraphQL schema

| Symptom | Cause | How to address |
| --- | --- | --- |
| Old queries suddenly fail validation | A field or argument was removed/renamed | Restore the field or run a deprecation phase |
| Old mutations fail to supply enough input | Added a required non-null input field | Use optional/defaulted fields or a new mutation |
| Clients crash upon receiving a new enum | Client codegen treats enums as closed sets | Add fallbacks or plan a separate contract |
| Clients can no longer distinguish null | Nullability changed | Evaluate semantics and generated types before changing |
| New and old fields return different data | Two resolvers maintain separate business logic | Share an application service and add contract tests |
| Removed a field, and partners break | Only checked internal traffic | Track external clients, scheduled jobs, and persisted operations |
| Schema diff detects no errors | Only semantics or authorization changed | Add consumer contract and integration tests |
| Deprecated field lingers indefinitely | No owner or removal criteria | Assign an owner, usage metrics, and sunset criteria |

## 14. Pre-release schema checklist

- Can this change be rolled out additively?
- Do existing queries and mutations still validate?
- Are any new arguments or input fields required?
- Has nullability changed?
- Do enums or unions add values/types that clients must handle?
- Is the old field marked `@deprecated` with a clear reason?
- Do old and new resolvers share the necessary business logic?
- Are metrics in place to track which clients still use the old field?
- Have persisted operations and client codegen been verified?
- Does CI include schema diffs and contract tests?
- Are communication, sunset, and rollback plans in place?

Schema evolution lets a GraphQL API serve multiple generations of clients on a single evolving contract. Favor adding optional fields and inputs, mark legacy fields with `@deprecated`, keep both contracts working during migration, and remove old fields only after usage is verified. For incompatible changes, publish a separate schema version with a clear lifecycle. Spring for GraphQL provides the resolvers and runtime to implement the contract; safeguarding compatibility remains the responsibility of schema design, release processes, and consumer testing.

## References

- [GraphQL Specification — Type System and Deprecation](https://spec.graphql.org/)
- [GraphQL — Schema and Queries](https://graphql.org/learn/schema/)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
