# Namespacing Queries

## 1. Why organize Queries into namespaces?

When a GraphQL API is small, the `Query` root type usually holds a handful of simple fields:

```graphql
type Query {
    book(id: ID!): Book
    books(first: Int): [Book!]!
    author(id: ID!): Author
    authors(first: Int): [Author!]!
    account(id: ID!): Account
    invoices(first: Int): [Invoice!]!
}
```

As the system grows, multiple domains add fields to `Query`. The root type turns into a long list, field names collide easily, ownership becomes harder to divide, and consumers struggle to explore the API.

Query namespacing is the practice of grouping fields by domain or capability using intermediate object types. Clients still send a single GraphQL operation to the same endpoint, while the field path in the query clearly expresses which business group the data belongs to.

Example:

```graphql
type Query {
    catalog: CatalogQueries!
    accounts: AccountQueries!
    billing: BillingQueries!
}
```

Instead of putting every field at the top level, the schema creates `catalog`, `accounts`, and `billing` groups.

## 2. Namespacing is not special GraphQL syntax

The GraphQL Specification does not define a `namespace` keyword or dedicated namespace mechanism for `Query`. It is a schema design pattern built out of ordinary object types and fields.

Distinguish schema namespacing from easily confused concepts:

| Concept | Example | Meaning |
| --- | --- | --- |
| Query namespace | `catalog { books { id } }` | Grouping schema fields via object types |
| Operation name | `query CatalogPage { ... }` | Client-chosen name for an operation |
| Alias | `recent: books(first: 5)` | Renaming a response key in a single call |
| Fragment | `...BookFields` | Reusing a selection set |
| HTTP path | `/graphql` | Endpoint receiving GraphQL requests |

Operation names, aliases, and fragments do not create schema namespaces. Namespacing is defined in SDL and is part of the public API contract.

## 3. One Query root and multiple grouping objects

Every GraphQL schema has exactly one root type for Query. By convention, this type is named `Query`; a schema can declare a different root name via a schema definition, but there is still only one query root. For example, `schema { query: RootQuery }` renames the root type—it does not create an independent extra namespace.

Namespacing does not create multiple Query roots. It adds fields on the Query root, each returning an object type representing a group of queries.

Full SDL example:

```graphql
type Query {
    catalog: CatalogQueries!
    accounts: AccountQueries!
    billing: BillingQueries!
}

type CatalogQueries {
    book(id: ID!): Book
    books(genre: String, first: Int = 20): [Book!]!
}

type AccountQueries {
    me: Account
    account(id: ID!): Account
}

type BillingQueries {
    invoice(id: ID!): Invoice
    invoices(first: Int = 20): [Invoice!]!
}

type Book {
    id: ID!
    title: String!
}

type Account {
    id: ID!
    displayName: String!
}

type Invoice {
    id: ID!
    total: Int!
}
```

`CatalogQueries`, `AccountQueries`, and `BillingQueries` are ordinary object types. They are not separate services, modules, or databases. Their primary purpose is to provide an easily discoverable, manageable field hierarchy.

Field names only need to be unique within the object type that defines them. Thus `CatalogQueries.book` and `AccountQueries.book` can share the same name without conflict; their schema coordinates differ. Conversely, all fields declared directly on `Query` still share a single namespace.

## 4. Clients querying across namespaces

Clients can select from one or multiple groups in the same operation:

```graphql
query Dashboard {
    catalog {
        books(genre: "SCIENCE", first: 5) {
            id
            title
        }
    }
    accounts {
        me {
            id
            displayName
        }
    }
    billing {
        invoices(first: 3) {
            id
            total
        }
    }
}
```

The GraphQL server still executes one operation against one schema. Namespaces are merely field branches in the selection set. Clients do not need to send separate requests to `/catalog`, `/accounts`, or `/billing`.

GraphQL lets clients select only the fields they need within each group, so a single screen can combine data from multiple domains without loading the entire namespace object.

## 5. Implementing the namespace root in Spring for GraphQL

The `Query.catalog` field must return an object to serve as the source for child fields. When the namespace exists purely to group queries, that object can be a marker object holding no business data.

Java type declaration:

```java
public record CatalogQueries() {
}
```

Resolver for the root field:

```java
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class CatalogNamespaceController {

    @QueryMapping
    public CatalogQueries catalog() {
        return new CatalogQueries();
    }
}
```

`@QueryMapping` defaults to mapping the method to the identically named field on root type `Query`. The `catalog()` method does not need to call the database because it merely creates the entry point for the `CatalogQueries` branch.

When using a non-null namespace (`catalog: CatalogQueries!`), the resolver must always return a non-null object. If the resolver returns null, GraphQL raises an error and applies null propagation per the schema.

## 6. Mapping child fields with `@SchemaMapping`

Fields inside `CatalogQueries` are handled like fields on any ordinary object type. Spring for GraphQL uses `@SchemaMapping` to map them:

```java
import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class CatalogQueriesController {

    private final BookService bookService;

    public CatalogQueriesController(BookService bookService) {
        this.bookService = bookService;
    }

    @SchemaMapping(typeName = "CatalogQueries", field = "books")
    public List<BookView> books(
            CatalogQueries source,
            @Argument("genre") String genre,
            @Argument("first") Integer first) {

        return bookService.findBooks(genre, first);
    }

    @SchemaMapping(typeName = "CatalogQueries", field = "book")
    public BookView book(
            CatalogQueries source,
            @Argument("id") String id) {

        return bookService.findBook(id);
    }
}
```

Spring passes the parent `CatalogQueries` object into the `source` parameter. `@Argument` parameters extract values from the child field's arguments. `BookService` is the application's business service.

`typeName` must match the object type name in SDL. If the method name matches the field name, you can omit `field` and declare only `@SchemaMapping(typeName = "CatalogQueries")`.

## 7. Splitting controllers by namespace

When each domain has many queries, you can split controllers by group to keep code easy to navigate:

```text
graphql/
├── namespace/
│   ├── CatalogNamespaceController.java
│   ├── AccountNamespaceController.java
│   └── BillingNamespaceController.java
├── catalog/
│   └── CatalogQueriesController.java
├── account/
│   └── AccountQueriesController.java
└── billing/
    └── BillingQueriesController.java
```

Namespace controllers resolve only root fields such as `catalog`, `accounts`, and `billing`. Domain controllers resolve child fields belonging to their respective object types.

Giving every namespace its own controller is not mandatory. You can group small mappings into a single controller if they share responsibility and stay maintainable. What matters is specifying `typeName` clearly so two methods never accidentally register the same schema coordinate.

## 8. Namespace pattern vs. prefixed fields

Object-type namespacing is not the only option. An API can keep `Query` flat while prefixing each field with its domain:

```graphql
type Query {
    catalogBook(id: ID!): Book
    catalogBooks(genre: String, first: Int): [Book!]!
    accountMe: Account
    accountById(id: ID!): Account
    billingInvoice(id: ID!): Invoice
    billingInvoices(first: Int): [Invoice!]!
}
```

Comparison:

| Criterion | Object namespace | Prefixed fields |
| --- | --- | --- |
| Query structure | Adds one nesting level | Flat on the `Query` root |
| Field names | Shorter names possible inside each object type | Requires globally unique names on `Query` root |
| Discoverability | Clients browse by domain group | Clients search by prefix or schema docs |
| Spring resolvers | Root uses `@QueryMapping`, child fields use `@SchemaMapping` | Fields use `@QueryMapping` |
| Query depth | Increases by one level | Adds no namespace depth |
| Best fit | Large APIs, clear domains, many related fields | Small APIs or when keeping the query root flat |

Choose the pattern based on schema size, how clients explore the API, and domain governance needs. Do not add a namespace merely to shorten field names if doing so makes queries overly deep and harder to read.

## 9. When should you create a namespace?

A namespace adds value when the fields inside it share a clear business relationship. For example, `catalog` holds `book`, `books`, `categories`; `accounts` holds `me`, `account`, `preferences`; `billing` holds `invoice`, `invoices`, `paymentMethods`.

Practical criteria:

- Many fields belong to the same domain or bounded context.
- Root field names start colliding as multiple domains use words like `list`, `search`, or `detail`.
- Clients frequently query multiple fields within the same group.
- A group can evolve independently with clear schema ownership.
- Root type clutter needs to be reduced as the API grows.

If `Query` only has a few simple fields, a flat root is usually easier to use. Namespacing is not an end in itself; it must make the schema clearer.

## 10. Choosing consistent namespace and type names

Namespace names are part of the public API, so they must be stable and descriptive of the domain. Root fields typically use nouns or domain names:

```graphql
type Query {
    catalog: CatalogQueries!
    accounts: AccountQueries!
    billing: BillingQueries!
}
```

Guidelines:

- Namespace fields should be nouns/domains, not verbs like `getCatalog`.
- Use plural or collective names when a namespace holds multiple queries, such as `catalog`, `accounts`, `billing`.
- Namespace types should use a recognizable suffix like `CatalogQueries` or `CatalogQuery` consistently across the schema.
- Avoid vague names like `data`, `common`, `misc`, or `manager`.
- Avoid putting database names, repository names, or microservice names into the public schema unless they represent stable business concepts.
- Never rename a namespace simply because an internal Java package or team was renamed.

GraphQL field names are case-sensitive. Pick a consistent convention—typically `camelCase` for fields and `PascalCase` for object types.

## 11. Place arguments on the field that actually uses them

Arguments should be declared on the field that filters, paginates, or identifies data. Do not place all arguments on the namespace root if they apply only to a single child query.

```graphql
type CatalogQueries {
    book(id: ID!): Book
    books(
        genre: String
        first: Int = 20
        after: String
        sort: BookSort = TITLE_ASC
    ): BookConnection!
}

enum BookSort {
    TITLE_ASC
    TITLE_DESC
    PUBLISHED_AT_DESC
}
```

In this example, `id` only makes sense for `book`; `genre`, `first`, `after`, and `sort` only make sense for `books`.

When multiple fields share a common group of inputs, create a dedicated `input` type for reuse. Do not build a massive input object just to lump unrelated arguments together.

## 12. Pagination and query limits inside namespaces

Namespacing does not change pagination semantics. List-returning fields still need item limits and a clear cursor/page strategy.

Connection example:

```graphql
type CatalogQueries {
    books(first: Int = 20, after: String): BookConnection!
}

type BookConnection {
    edges: [BookEdge!]!
    pageInfo: PageInfo!
}

type BookEdge {
    cursor: String!
    node: Book!
}

type PageInfo {
    hasNextPage: Boolean!
    endCursor: String
}
```

Set a sensible default limit, cap the maximum `first` in the resolver/service, and validate cursors. Namespaces do not protect the server from queries requesting excessive data.

## 13. A namespace is not a security boundary

Do not assume that because a field sits under `catalog`, every child field shares the same access permissions. A single query can span multiple namespaces and each field may enforce its own policy.

Examples:

- `catalog.books` may be public.
- `accounts.me` requires an authenticated user.
- `accounts.account(id)` may only permit viewing one's own account or require admin privileges.
- `billing.invoices` may require a finance scope.

Enforce permissions in the resolver/service that owns the data using Spring Security method security or your existing authorization layer. Placing fields inside the same namespace object is strictly schema organization—it does not establish an authorization boundary.

When enforcing field-level access control, ensure mappings and services check tenant, owner, and scope alike. Never trust a client-supplied ID simply because it sits under an authenticated namespace.

## 14. DataLoader and N+1 still apply as usual

Namespacing does not change how GraphQL resolves child fields. If `catalog.books` returns multiple `Book`s, nested fields like `Book.author` can still trigger N+1 queries.

You can use `@BatchMapping` as usual:

```java
import java.util.List;
import java.util.Map;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookAuthorController {

    private final AuthorService authorService;

    public BookAuthorController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<BookView, AuthorView> author(List<BookView> books) {
        return authorService.findAuthorsByBooks(books);
    }
}
```

Batch mapping batches author loading across multiple `Book`s within the same execution. Use `BatchLoaderRegistry` and `DataLoader` when you need finer control over cache/request scoping or batching behavior.

## 15. Handling errors on child fields

Errors raised by `catalog.books` or `billing.invoices` remain GraphQL errors at their respective fields. A namespace does not introduce a new error boundary.

Responses can return data from another namespace alongside the specific error path. To illustrate when `books` can be null, the schema must declare that field nullable:

```graphql
type Query {
    catalog: CatalogQueries!
    accounts: AccountQueries!
}

type CatalogQueries {
    books(first: Int): [Book!]
}

type Book {
    id: ID!
}

type AccountQueries {
    me: Account
}

type Account {
    id: ID!
    displayName: String!
}
```

The response can then preserve the namespace and independent data branches:

```json
{
  "data": {
    "catalog": {
      "books": null
    },
    "accounts": {
      "me": {
        "id": "user-1",
        "displayName": "An"
      }
    }
  },
  "errors": [
    {
      "message": "Unable to load books",
      "path": ["catalog", "books"]
    }
  ]
}
```

Choose appropriate nullability. If `books` is declared `[Book!]!`, a field failure can bubble up to the namespace or root under non-null propagation rules. Do not declare non-null just to make the response look tidy; verify whether the data truly always exists.

## 16. Namespacing Queries does not mean namespacing Mutations

Object grouping is syntactically possible for Mutations, but be careful with execution semantics. GraphQL executes fields directly on the mutation root serially in order. Nested fields inside an object returned by the mutation root do not automatically inherit those serial execution semantics.

Avoid using the following pattern to group side-effecting mutations as nested fields:

```graphql
type Mutation {
    catalog: CatalogMutations!
}

type CatalogMutations {
    createBook(input: CreateBookInput!): Book!
    deleteBook(id: ID!): Boolean!
}
```

`catalog` is the sole root mutation field. `createBook` and `deleteBook` are nested fields, not root mutation fields. If a client selects both, you cannot rely on mutation-root serial execution semantics to guarantee side-effect ordering between them.

For commands with side effects, keep fields directly on `Mutation` and use domain prefixes:

```graphql
type Mutation {
    catalogCreateBook(input: CreateBookInput!): Book!
    catalogDeleteBook(id: ID!): Boolean!
    billingPayInvoice(id: ID!): PaymentResult!
}
```

That way, root mutation fields still execute serially per GraphQL semantics. Only use nested mutation namespaces when you understand the implications and never rely on serial ordering across nested child fields.

## 17. Namespacing and query depth/complexity

Object namespaces add one level to field paths. For instance, `books { id }` becomes `catalog { books { id } }`. This raises the minimum query depth and can affect active query depth/complexity limits.

When migrating a large API to namespaces:

- Review `MaxQueryDepthInstrumentation` or current query depth limits.
- Check complexity calculators if they score by field level.
- Review persisted queries or allowlists since query documents change.
- Check client query generators and document-based cache keys.
- Measure latency and response size before and after the change.

Adding one namespace level usually adds no extra database round-trips if the root resolver simply returns a marker object. Still, it adds a field resolution step and one level of nesting in the execution tree.

## 18. Evolving from flat Queries to namespaced Queries

Do not remove old root fields immediately when introducing a new namespace. Roll it out in stages:

1. Keep the old fields and add the new namespace to SDL.
2. Map both old and new fields to the same business service to ensure consistent semantics.
3. Write contract tests covering both query paths.
4. Mark old fields with `@deprecated`, providing a reason and the replacement path.
5. Track usage by schema coordinate/client to know when removal is safe.
6. Announce a migration deadline and only remove old fields in a planned breaking change.

Example:

```graphql
type Query {
    books(first: Int): [Book!]!
        @deprecated(reason: "Use catalog { books(first: ...) }.")
    catalog: CatalogQueries!
}

type CatalogQueries {
    books(first: Int): [Book!]!
}
```

In Spring for GraphQL, both mappings can call the same `BookService`:

```java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<BookView> books(@Argument("first") Integer first) {
        return bookService.findBooks(first);
    }

    @SchemaMapping(typeName = "CatalogQueries", field = "books")
    public List<BookView> catalogBooks(
            CatalogQueries source,
            @Argument("first") Integer first) {
        return bookService.findBooks(first);
    }
}
```

`@deprecated` alerts clients and tooling about the old field, but does not automatically rewrite old queries to the new field. Clients still need to update their selection path from `books` to `catalog { books }`.

## 19. Aliases do not replace schema migration

GraphQL aliases can rename response keys within a single query:

```graphql
query {
    catalogBooks: catalog {
        books(first: 5) {
            id
            title
        }
    }
}
```

The alias `catalogBooks` exists only for that operation. It does not create a `catalogBooks` field in the schema and does not let other clients discover that name via introspection.

To preserve the legacy API during migration, keep the old field in SDL along with its resolver. Aliases are only useful when a client wants to rename response keys—for example, when querying the same field with different arguments.

## 20. Testing namespaced Queries with GraphQlTester

Test queries through the public GraphQL API rather than only calling Java resolvers directly. Example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.graphql.test.tester.GraphQlTester;

class CatalogNamespaceTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void readsBooksThroughCatalogNamespace() {
        graphQlTester.document("""
                query CatalogBooks {
                    catalog {
                        books(first: 2) {
                            id
                            title
                        }
                    }
                }
                """)
                .execute()
                .path("catalog.books")
                .entityList(BookView.class)
                .hasSize(2);
    }
}
```

This example assumes the test context already provides a `GraphQlTester`, such as via `@GraphQlTest` or a tester configured for the transport under test. For real HTTP calls, use `HttpGraphQlTester` to test the endpoint over HTTP.

Beyond the response, verify:

- The namespace root is non-null and matches the expected schema type.
- Arguments pass accurately to the right child field.
- Authorization is enforced per field.
- Pagination limits are applied.
- Child fields use DataLoaders or batch mappings where needed.
- Error paths include the right namespace and field name.
- Legacy flat fields and new namespaced fields return compatible data during migration.
- Schema introspection displays fields and deprecation reasons accurately.

## 21. Common design mistakes

| Issue | Consequence | How to fix |
| --- | --- | --- |
| Creating a namespace for every tiny group | Unnecessarily long and deep queries | Group only when domains/fields are cohesive |
| Using names like `common`, `data`, `misc` | Clients cannot tell what the group means | Use clear domain or capability names |
| Treating a namespace as an authorization boundary | Sensitive fields can be accessed improperly | Enforce permissions in the owning resolver/service |
| Calling backend in root resolver just to return namespace | Unnecessary round-trip | Return a marker object when the namespace holds no data |
| Using `@QueryMapping` on child fields | Mapping misses `Query` root vs. namespace type | Use `@SchemaMapping` with the namespace's `typeName` |
| Nesting side-effecting mutations | Loses serial guarantees across child mutations | Keep commands on mutation root with domain prefixes |
| Forgetting to raise query depth limits | Valid queries get rejected after adding namespaces | Re-evaluate depth/complexity limits |
| Removing old fields immediately when adding namespaces | Breaks older clients | Deprecate, monitor usage, then remove later |
| Using aliases as field replacements | Schema lacks the new field; tooling misses it | Add the new field in SDL and its resolver |
| Inconsistent or colliding namespace type names | Hard-to-read schema and naming conflicts | Pick distinct type names and follow a uniform convention |

## 22. Namespaced Query design checklist

- [ ] Keep a single Query root and create an object type for each needed namespace.
- [ ] Name namespace fields after domains or capabilities.
- [ ] Name namespace types consistently and recognizably.
- [ ] Only group fields with a clear business relationship.
- [ ] Place arguments on the child fields that actually use them.
- [ ] Use `@QueryMapping` for root namespace fields.
- [ ] Use `@SchemaMapping` for namespace child fields.
- [ ] Return a marker object when the namespace exists solely to group queries.
- [ ] Keep authorization in resolvers/services and verify tenant/owner/scope.
- [ ] Preserve pagination, DataLoaders, and error handling for child fields.
- [ ] Review query depth/complexity after adding a nesting level.
- [ ] Do not mechanically apply object namespacing to side-effecting mutations.
- [ ] Use `@deprecated` and track usage when replacing legacy fields.
- [ ] Test responses, error paths, security, and migrations with `GraphQlTester`.

## Conclusion

Query namespacing is a pattern for organizing the `Query` root using intermediate object types such as `CatalogQueries`, `AccountQueries`, and `BillingQueries`. It groups fields by domain, reduces root type clutter, and makes client queries easier to discover. It is not special GraphQL namespace syntax and does not create additional Query roots or endpoints.

In Spring for GraphQL, root namespace resolvers typically use `@QueryMapping` and return a marker object; child fields use `@SchemaMapping` with the corresponding `typeName`. Arguments, authorization, DataLoaders, pagination, and error handling continue operating under standard GraphQL semantics. Introduce namespaces only when they clarify the schema; account for query depth, migration from flat fields, and never assume nested mutations share the serial execution semantics of the mutation root.

## References

- [GraphQL Specification — Root Operation Types](https://spec.graphql.org/September2025/#sec-Root-Operation-Types)
- [GraphQL Specification — Objects and Fields](https://spec.graphql.org/September2025/#sec-Objects)
- [GraphQL Specification — Executing Mutations](https://spec.graphql.org/September2025/#sec-Normal-and-Serial-Execution)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [GraphQL — Schema and Type System](https://graphql.org/learn/schema/)
