# Schema Evolution with Interfaces

## Objectives

After this lesson, you will be able to:

- Explain an interface as a shared contract for multiple object types in GraphQL.
- Evaluate the impact of adding, renaming, or removing fields, or adding an object type implementing an interface.
- Plan schema changes in a backward-compatible direction.
- Use field deprecation, inline fragments, and __typename to support client transitions.
- Test interfaces and concrete types in Spring for GraphQL.

## Interface as a Shared Contract

A GraphQL interface describes a set of fields provided jointly by multiple object types. Clients can query a field returning an interface and select shared fields without knowing in advance which concrete object will be returned.

For example, a content application has books and articles. Both have an identifier and a title:

~~~graphql
interface SearchResult {
  id: ID!
  title: String!
}

type Book implements SearchResult {
  id: ID!
  title: String!
  isbn: String!
}

type Article implements SearchResult {
  id: ID!
  title: String!
  url: String!
}

type Query {
  search: [SearchResult!]!
}
~~~

SearchResult is the shared contract. Book and Article must provide the id and title fields. Each object type can still have its own fields, such as isbn or url.

Clients can query shared fields:

~~~graphql
query {
  search {
    id
    title
  }
}
~~~

If type-specific data is needed, clients use inline fragments:

~~~graphql
query {
  search {
    __typename
    id
    title
    ... on Book {
      isbn
    }
    ... on Article {
      url
    }
  }
}
~~~

__typename indicates the concrete object type of each element. The interface provides a stable entry point for shared data, while inline fragments let clients tap into type-specific fields.

## Why Do Interfaces Affect Schema Evolution?

An interface is a contract fulfilled together by multiple object types. When the contract changes, every object type implementing the interface must continue satisfying the new contract.

For example, if you add a publishedAt field to SearchResult, both Book and Article must have the corresponding field. That field may be nullable, yet it still must be declared on every object type implementing the interface. Nullable only means the returned value can be null; it does not make declaring the field optional.

This creates two dimensions when evolving a schema:

- **Client compatibility:** do existing operations remain valid and retain their intended meaning?
- **Server schema compatibility:** do all object types, resolvers, and data sources satisfy the new contract?

A change can be safe for clients yet still make the server schema invalid if an object type implementing the interface has not been updated.

## Evaluating Common Changes

| Change | Impact on Existing Clients | Impact on Implementing Object Types |
| --- | --- | --- |
| Add nullable field to interface | Typically additive for existing operations | All implementors must declare the new field |
| Add non-null field to interface | Existing operations may stay valid, but new data must always have a value | All implementors must declare and guarantee returning a non-null value |
| Add nullable argument to interface field | Existing clients can continue calling without passing the argument | Each implementing field must support the corresponding argument per contract |
| Remove or rename interface field | Breaking for clients querying that field | Implementors and resolvers must be updated |
| Change interface field type | May render client operations or data incompatible | Implementor return types must satisfy interface implementation rules |
| Add new object type implementing interface | May introduce a new __typename at runtime | The new object type must fully implement the interface fields |
| Remove an implementor | Clients may no longer receive a previously seen result type | Corresponding mappings and data sources need to be removed |

Do not look solely at whether a schema diff is classified as additive or breaking. Also inspect how clients handle __typename, how the server resolves runtime types, and actual data constraints.

## Adding a Field to an Interface

Suppose the application wants every search result to have a creation date. We want to add createdAt:

~~~graphql
interface SearchResult {
  id: ID!
  title: String!
  createdAt: DateTime
}
~~~

After adding it, every object type implementing the interface must declare the field:

~~~graphql
type Book implements SearchResult {
  id: ID!
  title: String!
  createdAt: DateTime
  isbn: String!
}

type Article implements SearchResult {
  id: ID!
  title: String!
  createdAt: DateTime
  url: String!
}
~~~

In this example, createdAt is nullable because legacy data might not store creation dates or one data source might not yet provide that information. Resolvers can return null for records lacking a value.

If declared as createdAt: DateTime!, every implementor must return a non-null value for every valid result. Before choosing non-null, verify historical data, data from integrated systems, and all resolver execution paths meet the condition.

### Staged Rollout

In systems with many implementors or multiple development teams, you can roll out a new field in stages:

1. Identify all object types currently implementing the interface and where their data is supplied.
2. Add the new field to each concrete object type first, along with its corresponding resolver or property.
3. Test concrete types, including older records that may lack data.
4. Once all implementors are ready, add the field to the interface so clients can query it directly on the abstract type.
5. Update clients and monitor errors, null values, and adoption of the new field.

Adding the field to concrete object types first lets clients that need it query the field via inline fragments. Once the interface is expanded, clients can switch to querying the shared field on the interface.

## Adding an Argument to an Interface Field

An interface can declare arguments on a field. For example:

~~~graphql
interface SearchResult {
  id: ID!
  title(locale: String): String!
}
~~~

Implementing object types must provide the title field with a compatible locale argument:

~~~graphql
type Book implements SearchResult {
  id: ID!
  title(locale: String): String!
  isbn: String!
}

type Article implements SearchResult {
  id: ID!
  title(locale: String): String!
  url: String!
}
~~~

When adding an argument to an interface field, the corresponding implementing fields must be updated. Prefer nullable arguments or arguments with defaults so existing clients can keep calling without passing the new value. Adding a non-null argument with no default forces clients to provide a value and can invalidate existing operations.

Arguments already exposed by the interface must have compatible names and types on implementing fields. An object type can have extra arguments of its own, though clients querying through the interface cannot use arguments that exist only on a concrete type.

## Adding a New Object Type Implementing an Interface

Another common change is adding a new result kind. For example, the system adds videos:

~~~graphql
type Video implements SearchResult {
  id: ID!
  title: String!
  createdAt: DateTime
  durationSeconds: Int!
  playbackUrl: String!
}
~~~

If the search query starts returning Video, existing clients can still read the shared id and title fields. However, the response may contain __typename: "Video" that clients have never seen before.

This is especially important for clients using code generation or handling results with an exhaustive switch. If a client assumes only Book and Article exist, encountering Video may cause it to drop data, show an error, or fail to handle the UI state.

Clients should include a default branch for unknown concrete types:

~~~typescript
switch (result.__typename) {
  case "Book":
    return renderBook(result);
  case "Article":
    return renderArticle(result);
  default:
    return renderGenericSearchResult(result);
}
~~~

This is a client-side example; the same principle applies to any language branching on __typename. Before introducing a new implementor into production results, test existing clients with an unrecognized concrete type.

Adding an implementor does not usually invalidate existing GraphQL operations, yet it can alter the runtime result set. Therefore, treat it as a behavior-impacting change and notify client-owning teams.

## Renaming or Removing Fields: Use Deprecation First

Renaming or deleting an interface field immediately can break every client querying that field. GraphQL provides the @deprecated directive to mark old fields and communicate the replacement:

~~~graphql
interface SearchResult {
  id: ID!
  title: String! @deprecated(reason: "Use displayTitle instead")
  displayTitle: String!
}
~~~

Implementing object types must provide both the old field and the new field during the transition period:

~~~graphql
type Book implements SearchResult {
  id: ID!
  title: String! @deprecated(reason: "Use displayTitle instead")
  displayTitle: String!
  isbn: String!
}

type Article implements SearchResult {
  id: ID!
  title: String! @deprecated(reason: "Use displayTitle instead")
  displayTitle: String!
  url: String!
}
~~~

A migration workflow can proceed as follows:

1. Add the new field and implement it across all implementors.
2. Keep the old field so existing clients continue working.
3. Mark the old field with @deprecated along with a reason and the replacement field name.
4. Update clients, documentation, and example operations to the new field.
5. Monitor telemetry or operation logs to identify clients still using the old field.
6. Remove the old field only after the transition window ends and dependent clients have been addressed.

Deprecation is a signal for tooling and developers, not an automatic block on clients querying the old field. The server still needs to track usage and follow a clear removal plan.

## Changing Return Types and Nullability

The return type of an interface field is a critical part of the contract. Changing from String to String!, from String to Int, or from one object type to another can affect clients.

GraphQL allows the return type of a field implementing an interface to be more specific in valid cases, such as an interface returning an abstract interface/object and an implementor returning a compatible concrete object type. However, changing the type on the interface itself can still impact operations and responses of every client querying through the interface.

Nullability requires careful consideration:

- Relaxing from non-null to nullable can force clients that assume a value is always present to handle null.
- Tightening from nullable to non-null is only safe if the server guarantees a value is always present; legacy data or resolvers can cause GraphQL to raise errors and propagate null up to the parent field.
- Changing scalar types or object structures can force clients to update models and response parsing.

Therefore, when changing a type or nullability, it is usually better to add a new field, migrate clients, and then deprecate the old field rather than modifying a widely used type in place.

## Using a New Interface When the Shared Contract Changes Significantly

If a new group of fields does not fit the current contract or a change risks affecting many clients, you can introduce a new interface and have object types implement both interfaces simultaneously.

~~~graphql
interface SearchResult {
  id: ID!
  title: String!
}

interface DatedSearchResult {
  id: ID!
  title: String!
  createdAt: DateTime!
}

type Book implements SearchResult & DatedSearchResult {
  id: ID!
  title: String!
  createdAt: DateTime!
  isbn: String!
}

type Article implements SearchResult & DatedSearchResult {
  id: ID!
  title: String!
  createdAt: DateTime!
  url: String!
}

type Query {
  search: [SearchResult!]!
  datedSearch: [DatedSearchResult!]!
}
~~~

Existing clients continue using search and SearchResult. New clients can use datedSearch to receive the extended contract. Once old clients have migrated, the team can evaluate deprecating the old API.

A new interface is not always necessary. It adds extra concepts and fields to the schema that must be maintained. Use this approach only when the two contracts truly have different lifecycles or compatibility requirements.

## Implementing Interfaces in Spring for GraphQL

At the controller layer, a query can return a list of objects belonging to multiple concrete types:

~~~java
@Controller
public class SearchController {

    private final SearchService searchService;

    public SearchController(SearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    public List<SearchResult> search() {
        return searchService.search();
    }
}
~~~

In this example, SearchResult is a domain-side Java type or abstraction implemented by both Book and Article classes. The GraphQL runtime needs to determine the concrete GraphQL object type for each result to produce __typename and resolve inline fragments.

If the default type resolution mechanism does not infer the right GraphQL type from Java objects, configure a TypeResolver via RuntimeWiringConfigurer. When adding a new implementor, update type resolution alongside the resolvers/services returning data:

~~~java
@Bean
RuntimeWiringConfigurer searchResultTypeResolver() {
    return wiringBuilder -> wiringBuilder.type(
        TypeRuntimeWiring.newTypeWiring("SearchResult")
            .typeResolver(environment -> {
                Object source = environment.getObject();
                if (source instanceof Book) {
                    return environment.getSchema().getObjectType("Book");
                }
                if (source instanceof Article) {
                    return environment.getSchema().getObjectType("Article");
                }
                if (source instanceof Video) {
                    return environment.getSchema().getObjectType("Video");
                }
                throw new IllegalStateException(
                        "Unsupported SearchResult source: " + source.getClass().getName());
            })
    );
}
~~~

This example illustrates mapping Java types to GraphQL object types. In a real application, handle unrecognized source objects with an explicit error or an appropriate fallback mechanism rather than silently returning null. Domain class names and structure may differ from the schema, so test type resolution with every implementor.

When modifying an interface, review all of these together:

- SDL of the interface and implementing object types.
- Resolvers for new fields on each concrete type.
- Services and data sources returning concrete objects.
- Type resolver if the application configures one manually.
- Client queries using shared fields, inline fragments, and __typename.

## Testing Interface Changes

GraphQlTester helps test operations against the schema and verify the concrete types returned. Example:

~~~java
graphQlTester.document("""
        query {
            search {
                __typename
                id
                title
                ... on Book {
                    isbn
                }
                ... on Article {
                    url
                }
            }
        }
        """)
    .execute()
    .path("search[0].__typename")
    .entity(String.class)
    .isEqualTo("Book");
~~~

When adding a field to an interface, test operations querying the new field via the interface and verify all implementors yield valid results. When adding a concrete type, verify type resolution returns the right __typename and the corresponding inline fragment works.

A schema evolution test suite should cover:

1. The schema remains valid with all object types implementing the interface.
2. Shared fields produce valid results on every concrete type.
3. Nullable fields handle legacy data lacking values.
4. Non-null fields never return null in any valid case.
5. New concrete types are recognized and return the right __typename.
6. Existing client queries still execute after additive changes.
7. Deprecated fields continue working during the migration period.
8. The type resolver raises a clear error when encountering an unsupported source object.

Beyond GraphQL-level tests, use schema diff or schema compatibility checks in CI to catch unexpected removed fields, type changes, nullability changes, or shifts in possible types. Static schema checks do not replace integration tests because they do not verify real data and resolver behavior.

## Safe Interface Evolution Workflow

When planning an interface change, you can follow this sequence:

~~~mermaid
flowchart TD
    A[Define change goal] --> B[List implementors and clients]
    B --> C[Classify schema and runtime impact]
    C --> D[Design additive change or new interface]
    D --> E[Update SDL, resolvers, and type resolution]
    E --> F[Test each concrete type and old clients]
    F --> G[Deploy and monitor telemetry]
    G --> H[Deprecate old field if applicable]
    H --> I[Remove after clients have migrated]
~~~

Before deploying, document:

- Which object types currently implement the interface.
- Which clients query shared fields or depend on __typename.
- Whether the new field has complete data across all sources.
- Whether the change requires new resolvers, type resolvers, or data migrations.
- Conditions and timeline for removing any deprecated field.

For changes affecting multiple teams, announce the schema change and transition schedule. This gives clients time to update code generation, caches, models, and handling for new concrete types.

## Common Mistakes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Schema fails to start after adding interface field | One or more object types have not declared the required interface field | Update all implementors and check schema validation |
| New field always returns null | Concrete type's resolver or data has not been updated | Check resolvers, properties, and historical data |
| GraphQL reports non-null error | An implementor returned null for a non-null field | Review data and choose nullable if the contract allows |
| Client fails to handle new result | New implementor added and __typename is unrecognized by client | Add a fallback branch and update clients |
| Inline fragment does not execute | Type resolution returns the wrong concrete type | Check TypeResolver and domain object mapping |
| Old clients break after changing a field | Old field removed or type changed too early | Restore field, add replacement field, and use deprecation |
| Schema diff reports unexpected change | Interface/implementor field or nullability edited unintentionally | Add schema compatibility checks to CI |

## Comprehensive Practice

Using the SearchResult schema with Book and Article, perform these changes:

1. Add a nullable createdAt: DateTime field to each object type first.
2. Add resolvers or createdAt data for Book and Article.
3. Add createdAt to the interface and test queries querying solely through SearchResult.
4. Add a Video object type implementing SearchResult; update services and type resolution as needed.
5. Test __typename, inline fragments, and the client fallback branch.
6. Add a displayTitle field, mark title as deprecated, and update clients to the new field.
7. Write a schema compatibility check to ensure the old field is not accidentally removed before migration completes.

After the exercise, explain which changes only add capabilities for clients, which changes can alter runtime results, and which changes force every implementor to update.

## Key Takeaways

An interface is a shared contract across multiple object types. Every implementing object type must provide the fields declared on the interface, including nullable fields. Therefore, adding a field to an interface requires updating all implementors; adding a new object type can change the __typename values clients receive. Prefer additive changes, use inline fragments for specific fields, add new fields before deprecating old ones, and remove old fields only after clients have migrated. In Spring for GraphQL, test resolvers, type resolution, and every concrete type with GraphQlTester alongside schema compatibility checks.
