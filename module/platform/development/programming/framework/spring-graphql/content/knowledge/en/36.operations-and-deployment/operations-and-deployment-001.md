# Schema validation in CI with Spring for GraphQL

A GraphQL schema is the contract between the server and its clients. A change might still allow the application to compile while causing operations in a mobile app, web app, or another service to become invalid. Therefore, CI needs to validate the schema across multiple layers: whether the SDL is valid, whether Spring can build the executable schema, whether actively used operations still validate, and whether the change is compatible with the published schema.

With Spring for GraphQL, startup validation is an important layer, but it is not enough on its own. An application can start up successfully while a client operation still queries a removed field or passes an argument of the wrong type. A solid pipeline combines Spring build/tests, operation document validation, and schema compatibility checks before merging or publishing.

## Four validation layers to include in CI

| Validation layer | Question to answer | Tools or approach |
| --- | --- | --- |
| SDL/schema validation | Does the schema follow GraphQL syntax, type references, and specification rules? | GraphQL parser/validator, GraphQL Inspector, Spring GraphQL schema initialization. |
| Runtime wiring validation | Can Spring create `GraphQlSource`, scalars, controller mappings, and runtime wiring? | Spring Boot context test, `@GraphQlTest`, `@SpringBootTest`. |
| Operation validation | Are client query/mutation/subscription documents valid against the new schema? | GraphQL Inspector `validate`, GraphQL Code Generator, or persisted operation checks. |
| Schema compatibility | Does the change remove or tighten a contract currently used by clients? | GraphQL Inspector `diff`, Apollo GraphOS schema checks, or an equivalent schema registry. |

No single tool replaces all four layers. For example, an SDL parser does not know about client operations; operation validation does not prove a resolver works properly; schema diff does not test the database or runtime authorization.

## 1. Validating SDL and the GraphQL type system

Before building the application, check `.graphqls`/`.graphql` files to catch structural errors:

- Invalid SDL syntax or duplicate declarations of types, fields, arguments, or enum values.
- Fields referencing a non-existent type.
- Input objects using output-only types or output fields using input-only types.
- Invalid Query/Mutation/Subscription root types.
- Interface implementations missing fields or having incompatible types.
- Unions containing members that are not object types.
- Default values incompatible with the declared type.
- Directives applied in invalid locations or with invalid arguments according to their definitions.

Example of an invalid schema because a field references an undeclared type:

```graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  author: AuthorProfile!
}
```

If `AuthorProfile` has not been declared anywhere in the schema, schema validation will fail. This check should run immediately after SDL changes so errors are caught before deployment.

### Spring for GraphQL builds the executable schema

Spring Boot loads schema resources and creates `GraphQlSource` during application context initialization. This process validates the schema when merging SDL files and applying runtime wiring. Errors such as missing types, unconfigured scalars, or invalid runtime wiring typically cause the context startup to fail.

With Spring Boot, default schemas are typically discovered under `classpath:graphql/**/`. A different location can be configured via `spring.graphql.schema.locations`. If the schema is split into multiple files by domain, CI must validate all files loaded together by the application; validating individual files in isolation can report missing types declared in another file or miss conflicts when merging the schema.

Verify the context with an application startup test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class GraphQlSchemaStartupTests {

    @Test
    void applicationContextBuildsGraphQlSchema() {
        // If the context initializes successfully, the schema and runtime wiring have been built.
    }
}
```

This test verifies that the application's schema resources and runtime configuration load properly. It does not replace operation validation, and it may require test fixtures or Testcontainers if the application context depends on external databases/services.

### Verifying the GraphQL runtime via `GraphQlTester`

To verify that the schema actually accepts operations, you can send a small request via `ExecutionGraphQlServiceTester`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class GraphQlRuntimeSchemaTests {

    @Autowired
    ExecutionGraphQlService graphQlService;

    @Test
    void rootQueryTypeIsAvailable() {
        var tester = ExecutionGraphQlServiceTester.create(graphQlService);

        tester.document("{ __typename }")
                .execute()
                .path("__typename")
                .entity(String.class)
                .satisfies(typeName -> assertThat(typeName).isEqualTo("Query"));
    }
}
```

`__typename` is a GraphQL meta field, so the test above verifies that the root query can be executed. Important operation tests should be added for real queries/mutations; testing `__typename` alone does not verify field mappings, authorization, or service behavior.

For slice tests, `@GraphQlTest` loads the required GraphQL components and selected controllers. For full integration tests, `@SpringBootTest` tests the entire application context configuration. Choose the appropriate scope to avoid making every schema test spin up unnecessary external dependencies.

## 2. Validating client operation documents

Valid SDL does not guarantee that existing operations will still run. For example, a schema change might remove `Book.subtitle`, rename the `id` argument to `bookId`, or change an enum value. The server can still build the new schema, but operations stored in web/mobile clients may no longer validate.

Store operation documents in the repository or retrieve them from a persisted operation registry. For example:

```graphql
# src/test/graphql/book-detail.graphql
query BookDetail($id: ID!) {
  book(id: $id) {
    id
    title
    subtitle
  }
}
```

Validate all documents against the candidate schema before merging. The GraphQL Inspector CLI provides the `validate` command:

```bash
npx graphql-inspector validate 'src/**/*.graphql' schema/current.graphql
```

This command checks whether operation documents are valid against the specified schema. In projects with multiple schema resources, `schema/current.graphql` needs to be a schema snapshot composed from the exact same set of SDL files that Spring Boot uses. Do not validate operations against a sample schema file that lacks real types or fields.

Operation validation catches errors such as:

- A client querying a removed field or type.
- A client passing a non-existent argument or an argument of the wrong type.
- A variable type incompatible with the argument.
- A query missing a selection set on an object field or having a selection set on a scalar.
- An enum literal no longer declared by the schema.
- A fragment referencing an invalid type condition.

Operation validation only checks the document and schema. It does not verify runtime variable values, data existence in the database, access permissions, or whether the resolver returns the expected result; those aspects require separate integration/contract tests.

### Sources of operation documents

CI should validate operations from sources actually managed by the organization:

1. Documents in frontend or backend consumer repositories.
2. Persisted queries published alongside the application.
3. The GraphQL platform's operation registry, if available.
4. A suite of operation contract tests stored in the server repository.

If clients reside in separate repositories, schema checks can run from client pipelines or by fetching published operation artifacts. Avoid validating only a small test directory and concluding that all active clients are compatible.

With an operation registry, distinguish between active operations and stale operations with no remaining traffic. Use usage history over an appropriate time window to decide when to deprecate/remove; an operation not appearing in the server repository does not mean no external client is calling it.

## 3. Comparing the candidate schema against a baseline schema

Schema diff compares the schema in a pull request against an accepted baseline, usually the schema on the main branch or a schema published in a registry. The goal is to detect changes that could break clients before release.

GraphQL Inspector provides the `diff` command:

```bash
npx graphql-inspector diff schema/baseline.graphql schema/current.graphql
```

In the command above, the first file is the baseline schema, and the second file is the pull request's candidate schema. Put diff in CI so the pipeline fails when there is a breaking change according to the rules/exit code of the CLI version pinned in the project. Do not pass the candidate schema as both inputs, as the result will detect no changes.

### Examples of changes to watch for

| Schema change | Risk to clients |
| --- | --- |
| Removing a field/type in use | Operations no longer validate. |
| Renaming a field or argument | Older clients referencing the old name will fail. |
| Adding a Non-Null argument without a default to an existing field | Existing operations that do not pass the argument become invalid. |
| Changing a nullable input field to Non-Null | Clients might omit it or send null; operations/variables may fail. |
| Removing an enum value used in input | Clients sending the old enum value are no longer valid. |
| Changing a Non-Null output to nullable | Clients might receive null even though older generated types expect a value. |
| Changing a nullable output to Non-Null | Usually safe for clients if the resolver guarantees it; check null propagation and data. |
| Adding a nullable output field | Usually does not affect existing operations. |
| Adding a nullable input field or one with a default | Usually does not require older clients to change requests. |

Compatibility classification depends on input/output position and list/item nullability. Do not look only at a `type changed` message: inspect client operations and runtime data. Some tools may classify changing a nullable output to Non-Null as a type change or warning; a human still needs to verify the resolver's guarantee.

### Breaking, dangerous, and non-breaking

- **Breaking:** existing operations no longer validate, or values that clients rely on are no longer guaranteed.
- **Dangerous:** the schema remains valid but may cause clients to change behavior, such as adding an enum value to an output that client generated code handles exhaustively.
- **Non-breaking:** extending the schema in a way that allows existing clients to continue operating, such as adding a nullable output field.

Adding an enum value is usually additive for inputs because the server accepts more values. For outputs, clients may use exhaustive switches or generated enums that lack a branch for the new value; therefore, consumer behavior must be evaluated rather than assuming every enum addition is safe.

Deprecating a field does not remove it and usually does not break existing operations. However, deprecation requires a migration period, usage tracking, and a separate removal step.

## 4. Using a schema registry and operation checks

For systems with multiple clients or multiple subgraphs, a schema registry stores published schemas, tracks operation usage, and runs compatibility checks against deployed variants.

Apollo GraphOS supports schema checks for candidate schemas in pull requests. A common workflow:

1. Publish or supply the candidate schema from a branch/CI.
2. Compare the candidate against the published schema of the target graph variant.
3. Check observed operations to identify which clients may be affected.
4. Post check results to the pull request so reviewers can decide whether to merge.

Example using the Apollo Rover CLI (requires a graph ref and `APOLLO_KEY` configured in CI secrets):

```bash
rover graph check my-graph@current --schema ./schema/current.graphql
```

`my-graph@current` is an example graph reference; replace it with the actual graph and variant. The check command uses the candidate schema to run schema/operation checks according to GraphOS settings. Pin the Rover version and inspect the check results; do not treat uploading or publishing a schema as equivalent to running compatibility checks.

With Federation, schemas must be validated at both the subgraph level and supergraph composition level. A subgraph SDL may be valid in isolation yet fail to compose with other subgraphs due to conflicts in types, keys, field ownership, or directives. Run subgraph checks/composition checks against the graph registry before deploying a gateway or subgraph.

A schema registry is helpful when operations live across multiple repositories or clients are released independently. If a project is small and all operations live in the same repository, GraphQL Inspector diff/validate alongside Spring integration tests may already suffice; do not add a registry just to have another tool.

## 5. Generating a consistent schema artifact for CI

The candidate schema used in diff and operation validation must accurately reflect the schema the application will run. This is easy to get wrong when Spring Boot loads multiple SDL files, custom scalars, or a schema extended via runtime wiring.

Example source layout:

```text
src/main/resources/graphql/
├── common.graphqls
├── catalog.graphqls
├── orders.graphqls
└── customers.graphqls
```

Ensure the pipeline checks the same set of resources, the same custom directives, and the same schema composition method. You can:

- Maintain a composed SDL artifact as the input for schema diff and operation validation.
- Use a project schema export task to generate the candidate artifact directly from the schema resources.
- Use schema registry/composition tooling to build the candidate from subgraph SDLs.

Do not create a manual `schema/current.graphql` and forget to update it when adding new `.graphqls` files. Otherwise, CI might pass even though the runtime schema has changed. Generate the artifact from the same source and store it as a build artifact so reviewers can download it.

Custom scalar and directive wiring must be tested at runtime. An SDL validator knows a scalar name is declared, but does not prove the Java parser/serializer handles it properly. Spring context tests and GraphQlTester integration tests cover this verification layer.

## 6. Example GitHub Actions pipeline

The example below assumes the repository has:

- A Gradle wrapper to run Spring tests.
- `schema/current.graphql` as the candidate SDL composed from schema resources.
- `schema/baseline.graphql` fetched from the base branch.
- Operation documents in `src/test/graphql/`.
- `@graphql-inspector/cli` pinned in `package-lock.json`.

```yaml
name: GraphQL schema checks

on:
  pull_request:
  push:
    branches: [main]

jobs:
  schema-validation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - uses: gradle/actions/setup-gradle@v4

      - name: Run Spring tests and build
        run: ./gradlew clean check

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: npm

      - name: Install schema tooling
        run: npm ci

      - name: Validate client operations
        run: npx graphql-inspector validate 'src/test/graphql/**/*.graphql' schema/current.graphql

      - name: Fetch base schema
        if: github.event_name == 'pull_request'
        env:
          BASE_REF: ${{ github.base_ref }}
        run: |
          git fetch origin "$BASE_REF" --depth=1
          git show "origin/$BASE_REF:schema/current.graphql" > schema/baseline.graphql

      - name: Check schema compatibility
        if: github.event_name == 'pull_request'
        run: npx graphql-inspector diff schema/baseline.graphql schema/current.graphql
```

In this example, `npm ci` uses the package lockfile to pin the CLI version. Add `@graphql-inspector/cli` to `devDependencies` and commit `package-lock.json`. If the repository uses Maven, replace `./gradlew clean check` with `./mvnw verify`.

For direct pushes to `main`, you can store the published schema as an artifact or fetch the baseline from the latest tag/release. Never use the candidate as its own baseline.

If the schema artifact is generated in Gradle, add the export step before the `validate`/`diff` commands and ensure `schema/current.graphql` already exists. The example above intentionally leaves out the export step because how SDL is exported depends on each application's schema resource layout and custom wiring.

## 7. Example GraphQL Inspector configuration

Pin the CLI in `package.json` so every developer machine and CI runner uses the same version:

```json
{
  "private": true,
  "devDependencies": {
    "@graphql-inspector/cli": "<pinned-version>"
  }
}
```

Replace `<pinned-version>` with a version tested by the project and commit the lockfile. Avoid running `npx` without a pinned version in critical pipelines because rules or exit behavior may change between runs.

Common commands:

```bash
# Validate operation documents
npx graphql-inspector validate 'src/test/graphql/**/*.graphql' schema/current.graphql

# Compare baseline and candidate schemas
npx graphql-inspector diff schema/baseline.graphql schema/current.graphql
```

For projects with multiple operation directories, pass appropriate globs covering all client documents within your scope of control. For projects using GraphQL Config, you can declare schema/documents in a shared configuration so editors, codegen, and CI use the same source.

## 8. Integrating schema checks into the pull request workflow

A pull request that changes the schema should provide enough information for reviewers to evaluate:

- SDL diff: which fields/types/arguments/inputs/enums/directives were added, modified, or removed.
- Compatibility result: breaking/dangerous changes and affected operations.
- Runtime test result: `GraphQlSource` initialization, scalar/wiring functionality, and critical operation tests passing.
- Ownership: which domains/clients are affected and who confirms the migration.
- Rollout plan: adding new fields, deprecating old fields, monitoring usage, and scheduling removal.

CI should block merges when the schema is invalid, internal operations fail to validate, or there is an unapproved breaking change. Dangerous changes may require additional review rather than automatically blocking in every project.

For intentional breaking changes, do not disable all schema checks. Establish an exception process documenting the reason, affected clients/operations, release plan, and approvers. You can use a separate version/variant or staged rollout if clients cannot update simultaneously.

## 9. Common CI setup pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Spring tests pass, yet clients fail after deployment | Only application startup was checked without validating operation documents. | Add operation validation for documents and registries. |
| SDL diff reports no changes despite schema edits | Baseline and candidate point to the same artifact, or candidate was not re-exported. | Check both inputs and add an explicit schema artifact generation step. |
| CLI reports missing types when run on a single file | The actual schema is composed from multiple `.graphqls` resources. | Validate/diff the composed schema from all resources. |
| Operation validation passes, yet runtime fails | Custom scalars, directives, controller mappings, or service wiring are not verified by static validation. | Add Spring context and GraphQlTester integration tests. |
| Schema diff misses external clients outside the repository | Client operation documents are not included in CI or a registry. | Connect an operation registry/consumer artifacts and monitor usage. |
| Adding an enum value breaks a client | Generated client code uses exhaustive switches or strict enum mappings. | Treat output enum additions as dangerous and verify consumers. |
| CI cannot find the baseline schema | Base branch was not fetched, or artifact paths differ between branches. | Fetch the base ref and verify paths/schema export steps. |
| Check results fluctuate unpredictably | CLI/tool versions are not pinned. | Pin dependencies, lockfiles, Rover version, and rule configurations. |
| Subgraphs are valid, yet the gateway fails to compose | Only subgraph SDL was checked without checking supergraph composition. | Add Federation composition/schema registry checks. |
| Schema checks pass, yet resolvers return wrong data | Compatibility checks do not test business behavior. | Add resolver, authorization, and database integration tests. |

## 10. CI schema validation checklist

- [ ] All schema resources are combined into a single candidate schema.
- [ ] SDL parsing and GraphQL type-system validation pass.
- [ ] Spring application context creates `GraphQlSource` and runtime wiring.
- [ ] Custom scalars/directives and critical controller mappings have integration tests.
- [ ] Client operation documents are validated against the candidate schema.
- [ ] Candidate is diffed against the proper baseline from the base branch or schema registry.
- [ ] Breaking/dangerous changes have clear owners and decisions.
- [ ] Federation subgraph composition is checked if the system uses Federation.
- [ ] CLI, schema tooling, and dependency versions are pinned.
- [ ] Schema artifacts and check results are saved in CI for reviewer inspection.

## Summary

Schema validation in CI requires multiple layers. Spring Boot context tests confirm that the schema and runtime wiring can be built; GraphQL Inspector `validate` confirms that operation documents remain valid; `diff` or schema registry checks detect contract changes that could impact clients. With multiple clients or Federation, persisted operations and composition checks must be included in the pipeline.

Keep the candidate schema consistent with all `.graphqls` resources actually loaded by the application. Pin tools, compare against the right baseline, verify runtime behavior with GraphQlTester, and require reviews for breaking/dangerous changes. A green CI build only confirms the contracts included in checks; unregistered external operations and business behavior still need to be governed through registries, monitoring, and integration tests.

## References

- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Boot — GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL Inspector — CLI](https://the-guild.dev/graphql/inspector/docs/essentials/cli)
- [Apollo Rover — `graph check`](https://www.apollographql.com/docs/rover/commands/graphs)
- [Apollo GraphOS — Schema Checks](https://www.apollographql.com/docs/graphos/platform/schema-management/checks)
- [GraphQL Specification — Validation](https://spec.graphql.org/September2026/#sec-Validation)
