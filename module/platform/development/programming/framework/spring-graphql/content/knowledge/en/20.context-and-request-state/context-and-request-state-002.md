# LocalGraphQlContext in Spring for GraphQL

## Objectives

After this lesson, you will be able to:

- Explain local context during GraphQL execution and why data needs to be passed down a field branch.
- Distinguish execution-wide **GraphQLContext** from the local context of a field and its child fields.
- Use **DataFetcherResult.localContext(...)** to pass data from a parent resolver down to child resolvers.
- Read local context values using **@LocalContextValue** in an annotated controller.
- Distinguish source objects, GraphQL context, and local context.
- Choose appropriate data to place in local context, such as policies, tenant scope, or precomputed metadata.
- Understand inheritance scope, overriding, and limitations of local context in the selection tree.
- Avoid using local context as a session, global cache, or standalone authorization mechanism.
- Test context propagation across nested fields using **GraphQlTester**.

## 1. What problem does local context solve?

A GraphQL operation may resolve a parent object first and then resolve multiple child fields of that object. In some cases, the parent resolver has already computed metadata that the child resolvers need.

For example, when loading a book, the resolver may determine the tenant containing the book, whether the user can view internal notes, the locale used to format data, or a policy computed from the data and current permissions.

If each nested resolver recomputes this metadata, the application may duplicate work or call services again. If it is stored in a field of a singleton controller, concurrent requests can overwrite each other's state.

Local context provides an internal data channel from a parent field to child fields within its execution branch. This data does not become a field in the GraphQL response and does not need to be sent back by the client.

Example operation:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
        internalNotes
        author {
            id
            name
        }
    }
}
~~~

The `Query.book` resolver can build the metadata once. The `Book.internalNotes`, `Book.author`, or deeper child field resolvers can receive that metadata via local context.

## 2. Distinguishing GraphQLContext and local context

Spring for GraphQL works with two kinds of context that have different scopes.

| Characteristic | GraphQLContext | Local context |
| --- | --- | --- |
| Scope | Entire GraphQL execution | A field and child fields within its branch |
| Creation source | Request, interceptor, or execution input | Result returned by the parent field's DataFetcher |
| GraphQL Java API | DataFetchingEnvironment.getGraphQlContext() | DataFetchingEnvironment.getLocalContext() |
| Binding in annotated controller | @ContextValue | @LocalContextValue |
| Purpose | Request-wide info such as principal, tenant, locale | Branch-specific metadata such as policy or precomputed data |
| Relationship across branches | Accessible by resolvers within the same execution | Not automatically shared with sibling branches or other root fields |

GraphQLContext suits data shared across the operation, such as the tenant and principal determined from the request. Local context suits data that only makes sense when resolving a specific object and its child fields.

For example:

- `tenantId` determined from the request's authentication info: usually belongs in GraphQLContext.
- `canReadInternalNotes` computed for a specific book: can belong in the local context of Book.
- `authorDisplayPolicy` applying only to the `Book.author` branch: can be passed onward using local context on that branch.

Do not put all data into the same context. Choose the smallest scope that satisfies the resolver's needs.

## 3. A source object is not local context

Nested resolvers typically receive a source object representing the parent object being resolved. For example:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

The `book` parameter is the source object. It holds the book's data and is the value on which the `Book.author` field is being resolved.

Local context is an auxiliary channel. It can hold metadata that does not belong to the domain object and does not need to appear in the GraphQL schema.

We can distinguish:

- **Source object:** the parent object that the child field reads or uses to compute its result.
- **GraphQLContext:** execution-wide shared data.
- **Local context:** internal data passed from a parent field down to child fields.

There is no need to stuff temporary metadata into an entity or DTO just to pass it to a resolver. If the data is only meaningful within a branch of the selection tree, local context may be a better fit.

## 4. Passing local context with DataFetcherResult

GraphQL Java provides `DataFetcherResult` so a DataFetcher can return data alongside execution metadata. In Spring for GraphQL, an annotated controller can return `DataFetcherResult<T>`.

The `data` part holds the value of the GraphQL field. The `localContext` part provides the context object for that value's child fields.

Example schema:

~~~graphql
type Book {
    id: ID!
    title: String!
    internalNotes: String
}

type Query {
    book(id: ID!): Book
}
~~~

Define the metadata for child fields:

~~~java
public record BookFieldPolicy(
        boolean canReadInternalNotes,
        String locale) {
}
~~~

Parent resolver:

~~~java
import graphql.execution.DataFetcherResult;
import java.util.Map;
import java.util.UUID;

@Controller
class BookQueryController {

    private final BookService bookService;
    private final BookPolicyService policyService;

    BookQueryController(
            BookService bookService,
            BookPolicyService policyService) {
        this.bookService = bookService;
        this.policyService = policyService;
    }

    @QueryMapping
    public DataFetcherResult<Book> book(@Argument("id") UUID id) {
        Book book = bookService.findById(id);
        BookFieldPolicy policy = policyService.policyFor(book);

        return DataFetcherResult.<Book>newResult()
                .data(book)
                .localContext(Map.of("bookPolicy", policy))
                .build();
    }
}
~~~

When GraphQL resolves `Query.book`, the response data is still the `Book` object. The Map passed into local context is only for resolving child fields.

Local context is not serialized as an extra field in the response. The client only receives the fields selected in the schema, such as `id`, `title`, and `internalNotes`.

## 5. Reading local context with @LocalContextValue

A child resolver can receive a value from local context using `@LocalContextValue`:

~~~java
import org.springframework.graphql.data.method.annotation.LocalContextValue;

@Controller
class BookDetailsController {

    private final BookDetailsService detailsService;

    BookDetailsController(BookDetailsService detailsService) {
        this.detailsService = detailsService;
    }

    @SchemaMapping(typeName = "Book", field = "internalNotes")
    public String internalNotes(
            Book book,
            @LocalContextValue("bookPolicy") BookFieldPolicy policy) {

        if (!policy.canReadInternalNotes()) {
            return null;
        }

        return detailsService.findInternalNotes(book.getId(), policy);
    }
}
~~~

In this example:

- `Book` is the source object.
- `@LocalContextValue("bookPolicy")` retrieves the entry with key `bookPolicy` from local context.
- `BookFieldPolicy` is the Java type of the passed value.
- The resolver uses `policy` to decide how to fetch the `internalNotes` field.

The schema declares `internalNotes: String`, which is a nullable field. Therefore the example can return `null` when the user is not allowed to view the field. If the schema declares a non-null field, you must choose how to represent access denial and handle errors according to that contract.

Local context only helps pass the policy to the resolver. The service still needs to protect sensitive data across every access path that can invoke it; do not treat having a boolean value in context as the sole security boundary.

## 6. Naming and structuring local context

When local context holds multiple values, use stable and meaningful keys. You can group metadata into a record instead of passing multiple scattered values:

~~~java
public record BookLocalContext(
        BookFieldPolicy policy,
        String correlationId) {
}
~~~

Parent resolver:

~~~java
BookLocalContext localContext = new BookLocalContext(
        policyService.policyFor(book),
        correlationId
);

return DataFetcherResult.<Book>newResult()
        .data(book)
        .localContext(Map.of("bookContext", localContext))
        .build();
~~~

Child resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "internalNotes")
public String internalNotes(
        Book book,
        @LocalContextValue("bookContext") BookLocalContext context) {

    return detailsService.findInternalNotes(
            book.getId(),
            context.policy()
    );
}
~~~

A record structure groups related values, reduces the number of keys to manage, and makes clear what data type the resolver expects.

Some guidelines:

- Use specific key names, avoiding generic keys like `data`, `value`, or `context`.
- Use records or immutable objects whenever possible.
- Do not store mutable state that could be modified concurrently by multiple resolvers.
- Do not put the entire request or a large entity graph into local context if only a few pieces of metadata are needed.
- Do not store tokens, credentials, or secrets if the resolver does not genuinely need them.

## 7. Local context scope in the selection tree

Local context is passed from a parent field to that field's child fields. It is scoped by the GraphQL execution tree, not as a global variable.

Example:

~~~graphql
query {
    book(id: "book-42") {
        title
        internalNotes
        author {
            name
            biography
        }
    }
    publicCatalog {
        title
    }
}
~~~

If `Query.book` returns a `DataFetcherResult` with local context:

- `Book.title` can be resolved inside the `book` branch.
- `Book.internalNotes` can read the local context of `book`.
- `Book.author` is also inside the `book` branch.
- `Author.name` and `Author.biography` are deeper child fields of that branch.
- `Query.publicCatalog` is another root branch and does not automatically receive the local context created by `Query.book`.

This keeps each branch's metadata separate. The local context of one book does not automatically become the local context of another root field.

Visualized:

~~~mermaid
flowchart TD
    Q["Query execution"] --> B["Query.book"]
    Q --> C["Query.publicCatalog"]
    B -->|local context: bookPolicy| T["Book fields"]
    T --> N["Book.internalNotes"]
    T --> A["Book.author"]
    A --> D["Author.name"]
    A --> E["Author.biography"]
~~~

## 8. Passing context deeper and overriding local context

A child resolver can also return `DataFetcherResult` to provide appropriate local context for its own child fields.

For example, `Book.author` needs a dedicated policy for the `Author` branch:

~~~java
public record AuthorFieldPolicy(boolean showBiography) {
}
~~~

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public DataFetcherResult<Author> author(
        Book book,
        @LocalContextValue("bookContext") BookLocalContext bookContext) {

    Author author = authorService.findById(book.getAuthorId());
    AuthorFieldPolicy authorPolicy =
            authorPolicyService.policyFor(author, bookContext.policy());

    return DataFetcherResult.<Author>newResult()
            .data(author)
            .localContext(Map.of("authorPolicy", authorPolicy))
            .build();
}
~~~

A deeper resolver can read the new policy:

~~~java
@SchemaMapping(typeName = "Author", field = "biography")
public String biography(
        Author author,
        @LocalContextValue("authorPolicy") AuthorFieldPolicy policy) {

    if (!policy.showBiography()) {
        return null;
    }

    return author.getBiography();
}
~~~

When a field returns a `DataFetcherResult` with a new local context, that context is used for the child fields of the returned value. If you need to retain data from the previous context, explicitly combine the required data into the new context object.

Do not assume a new context automatically merges every key from the previous context. Designing a record per branch makes it explicit which metadata is forwarded.

## 9. Local context and GraphQLContext in the same resolver

A resolver may need both request-wide shared data and branch-specific metadata.

Example:

~~~java
@SchemaMapping(typeName = "Book", field = "internalNotes")
public String internalNotes(
        Book book,
        @ContextValue("tenantId") UUID tenantId,
        @LocalContextValue("bookPolicy") BookFieldPolicy policy) {

    return detailsService.findInternalNotes(
            book.getId(),
            tenantId,
            policy
    );
}
~~~

In this example:

- `tenantId` comes from GraphQLContext, which is scoped to the entire execution.
- `policy` comes from local context passed down by the parent field.
- `book` is the source object of the nested field.

This combination avoids threading request-wide data through every object level when many resolvers need it. At the same time, metadata that only applies to a single branch remains confined to local context.

`@ContextValue` and `@LocalContextValue` do not replace each other. Choose the annotation based on where the value is created and the scope where it needs to be accessed.

## 10. When should you use local context?

Local context fits when a parent resolver already has data needed by multiple child fields, and that data is only meaningful within that branch.

| Scenario | Value that can be passed |
| --- | --- |
| Parent resolver already determined a policy for an object | Field display policy or permissions |
| Parent resolver already determined an object-specific locale | Locale or formatting rules |
| A branch needs a precomputed projection | Metadata about loaded fields or projection state |
| Nested resolver needs correlation metadata | Correlation ID or appropriate tracing information |
| Multiple child fields share a lightweight computed result | Precomputed result or metadata |

Local context is not the right choice for every kind of state. If information is needed across the entire execution, use GraphQLContext. If data is truly part of the domain object and needs to be returned to the client, model it as a field or DTO. If caching across requests is needed, use service-layer caching or a dedicated caching system.

## 11. When should you not use local context?

Do not use local context to:

- Store long-lived login state or replace the security context.
- Share data between independent GraphQL requests.
- Build a global cache or cross-request cache.
- Pass data to a sibling root field outside the current branch.
- Replace the source object when the data is genuinely part of the domain model.
- Store a large object just to avoid clean service/API design.
- Pass mutable state across resolvers that may execute concurrently.

Local context exists to support a single execution tree. It is not an HTTP session, not a request-scoped Spring bean, and not a thread-local.

## 12. Local context in nested lists

A parent field can return a list of objects:

~~~graphql
type Query {
    books: [Book!]!
}
~~~

If the `Query.books` resolver returns `DataFetcherResult<List<Book>>` with local context, that context is passed to the child fields of the list result within the `books` branch.

This works well when the metadata is the same for the entire list, such as a locale or a shared policy for that operation.

If each element in the list needs its own metadata, do not place a single map in the list's local context and assume it changes per `Book`. The local context of the list result belongs to the `books` field; it does not automatically create a different context for each element.

For per-item metadata, you can:

- Put item-specific metadata into a source DTO/wrapper.
- Resolve the metadata inside a field on each item.
- Create a dedicated item resolver that returns `DataFetcherResult` per item if the architecture and runtime support it.

Choose the representation so that data is attached to the right object and the right scope.

## 13. Nulls, errors, and missing local context values

A resolver should only require a local context key when the parent field guarantees providing that key.

For example, if `Book.internalNotes` always needs `bookPolicy`, every path resolving a `Book` with this field must create the corresponding local context. If another root resolver also returns `Book` without providing the key, the child resolver may fail to bind the expected value.

Ways to handle this:

- Ensure every parent resolver follows the same local context contract for that type/field.
- Use a consistent DTO/context type structure.
- If the value is genuinely optional, declare appropriate optional binding and handle the absent case.
- Write tests for every path that produces the same GraphQL type.

Do not use a permissive default like `false` just to mask a parent resolver forgetting to provide context if doing so changes visibility policies or access control.

Local context also does not bypass SDL nullability rules. If a nested field is non-null but the resolver returns `null` due to missing context or policy denial, GraphQL still applies null propagation according to the schema. Design the output contract and error policy consistently.

## 14. Security and sensitive data

Local context can contain information such as tenant scope or computed policies. Therefore, treat it as internal server data.

Principles:

- Only derive tenant and principal from trusted authentication sources.
- Never allow the client to send local context directly via GraphQL variables.
- Do not put access tokens, refresh tokens, or credentials into local context.
- Do not return local context in the GraphQL response or log entire context objects.
- Use immutable values so other resolvers cannot mutate shared metadata.
- Check permissions at the service/data access layer for sensitive data.
- Do not assume the presence of local context means the caller is authorized.

For example, `BookFieldPolicy` can help a resolver decide whether to display a field, but the service accessing internal data still needs to enforce appropriate authorization rules. This protects the data when the service is called from another resolver or from another business flow.

## 15. Testing local context with GraphQlTester

You should test end-to-end from the parent resolver to the nested resolver using a real GraphQL operation. Tests should verify:

1. The parent resolver returns the expected object in `data`.
2. The parent resolver attaches the local context.
3. The nested resolver receives the right key via `@LocalContextValue`.
4. The local context value affects the field result as expected.
5. Local context does not appear in the response.

Example test:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-42") {
                id
                title
                internalNotes
            }
        }
        """)
        .execute()
        .path("book.id")
        .entity(String.class)
        .isEqualTo("book-42")
        .path("book.internalNotes")
        .entity(String.class)
        .isEqualTo("Internal editorial note");
~~~

This test assumes the parent resolver creates a `bookPolicy` allowing notes to be read and the nested resolver uses that local context. You can add a test where the policy denies access to verify that the nullable field returns `null` or returns an error according to application policy.

You should also test:

- The parent resolver returning a plain object without local context.
- A deeper resolver returning `DataFetcherResult` with a new context.
- Two root fields having different local contexts.
- Multiple items in a list sharing the list's context.
- A child field not finding a required key.
- The GraphQL response not containing local context keys or objects.

## 16. Common errors

| Symptom | Cause | How to fix |
| --- | --- | --- |
| `@LocalContextValue` does not receive a value | Parent resolver did not return local context or wrong key | Check `DataFetcherResult.localContext` and the key name |
| Nested resolver receives null | Branch of the GraphQL type was produced by another parent resolver that did not provide context | Standardize the contract across parent resolvers |
| Using `@ContextValue` does not see local context | Accidentally reading execution-wide GraphQLContext | Use `@LocalContextValue` for local context |
| Using `@LocalContextValue` for shared tenant returns no value | Tenant was only placed in GraphQLContext | Use `@ContextValue` or explicitly pass tenant into local context |
| Context from one branch appears in another branch | Storing state in a singleton or static field | Pass per branch via `DataFetcherResult` |
| Deep resolver no longer sees old key | An intermediate parent resolver returned a new local context without retaining needed keys | Combine forwarded metadata into the new context |
| Local context is unexpectedly modified | Using a mutable Map/object shared across multiple resolvers | Use immutable records and collections |
| List local context does not differ per item | Placing per-item metadata at the list result level | Put metadata into the source item or per-item resolver |
| Sensitive data is still accessible via another service | Relying solely on policy in local context | Enforce authorization at the service/data access layer |
| Tests pass but production lacks context | Only tested one parent resolver path | Test every resolver that can return the same GraphQL type |

## 17. LocalGraphQlContext design workflow

When you need to pass metadata from a parent resolver down to child fields, follow this sequence:

1. **Identify where the data is created.** Is the value derived from the overall request or from a specific object?
2. **Choose the right context type.** Use GraphQLContext for the entire execution; use local context for a single field branch.
3. **Identify the source object.** Do not confuse the source with internal metadata.
4. **Define the context type.** Prefer clearly named records or immutable objects.
5. **Return `DataFetcherResult`.** Place GraphQL data in `data` and metadata in `localContext`.
6. **Bind in the child resolver.** Use `@LocalContextValue` with consistent keys.
7. **Review deeper fields.** If a new context is needed, explicitly forward the data that must be kept.
8. **Check all parent resolvers.** The same GraphQL type may be returned by multiple root fields.
9. **Evaluate nullability and security.** Missing context must never silently turn into granted access.
10. **Test with `GraphQlTester`.** Cover multiple branches, nested lists, and missing context cases.

## 18. Summary

Local context is an internal data channel from a GraphQL field to child fields within that field's execution branch. In Spring for GraphQL, a parent resolver can return `DataFetcherResult<T>` and use `localContext(...)` to attach metadata; child resolvers read values with `@LocalContextValue`.

Local context differs from `GraphQLContext` in scope: `GraphQLContext` is shared across the execution, whereas local context is bound to a field branch. It also differs from the source object because it only carries auxiliary metadata and does not replace the parent object. Using local context for policies or precomputed data avoids duplicate work and keeps internal metadata out of the GraphQL schema. Keep context immutable, do not use it as a cross-request cache or standalone authorization mechanism, and test the entire propagation path from parent resolver to nested fields with `GraphQlTester`.
