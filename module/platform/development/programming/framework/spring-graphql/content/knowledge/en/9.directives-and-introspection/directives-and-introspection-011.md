# Directives and Authorization in GraphQL

## Objectives

After this lesson, you will be able to:

- Explain what a directive is and how directives add behavior or metadata to a GraphQL schema and operations.
- Distinguish between directives used in operations and directives attached to the schema.
- Use built-in directives such as `@include`, `@skip`, `@deprecated`, and `@specifiedBy`.
- Declare custom directives to describe access policies.
- Understand why declaring an authorization directive in SDL does not protect data by itself.
- Protect Query, Mutation, and nested fields with Spring Security in Spring for GraphQL.
- Combine authority, role, and per-object access checks.
- Identify access paths commonly missed via aliases, fragments, nested fields, and DataLoader.
- Test authorization behavior and handle errors without leaking sensitive data.

## 1. What Is a Directive?

A directive is a GraphQL construct used to add instructions or metadata to schemas and operations. A directive name starts with `@`, followed by the directive name and optional arguments.

Directives can appear in two main scopes:

- **Executable directives** are written in operations sent by clients. They affect how part of an operation is executed.
- **Schema directives** are attached to definitions of types, fields, arguments, scalars, or other schema elements. They describe schema-related metadata or policies.

Example of an operation using a directive:

~~~graphql
query GetBook($id: ID!, $showAuthor: Boolean!) {
    book(id: $id) {
        title
        author @include(if: $showAuthor) {
            name
        }
    }
}
~~~

When `showAuthor` is `true`, the `author` field is included in execution. When `false`, that field is skipped.

Example of a directive on a schema:

~~~graphql
type Book {
    id: ID!
    title: String!
    oldTitle: String @deprecated(reason: "Use title instead")
}
~~~

`@deprecated` marks the `oldTitle` field as no longer recommended for use. Introspection tools can display this information to clients and IDEs.

Directives do not replace fields or types. They attach extra information or rules to a valid location in a GraphQL document or schema.

## 2. Directive Declaration Syntax and Locations

A directive is declared using the `directive` keyword:

~~~graphql
directive @audit(action: String!) on FIELD_DEFINITION
~~~

In this declaration:

- `@audit` is the directive name.
- `action: String!` is a required argument of the directive.
- `FIELD_DEFINITION` is the location where the directive is allowed to be attached.

A directive can apply to multiple locations by listing them separated by `|`:

~~~graphql
directive @example on FIELD | FRAGMENT_SPREAD | INLINE_FRAGMENT
~~~

Some common locations:

| Location | Meaning |
| --- | --- |
| `FIELD` | Field in an executable operation |
| `FRAGMENT_SPREAD` | Location where a fragment is spread |
| `INLINE_FRAGMENT` | Inline fragment in an operation |
| `OBJECT` | Object type in the schema |
| `FIELD_DEFINITION` | Field defined in the schema |
| `ARGUMENT_DEFINITION` | Argument of a field or directive |
| `INPUT_FIELD_DEFINITION` | Field inside an input object |
| `ENUM_VALUE` | Enum value |
| `SCALAR` | Custom scalar |
| `INTERFACE` | Interface type |
| `UNION` | Union type |

A directive may only be used at its declared locations. Attaching a directive to an invalid location causes the schema or operation to fail validation.

### 2.1. Directives with Arguments

Directives can accept arguments just like fields:

~~~graphql
directive @cacheControl(
    maxAge: Int!
    scope: CacheScope = PUBLIC
) on FIELD_DEFINITION

enum CacheScope {
    PUBLIC
    PRIVATE
}

type Query {
    publicCatalog: [Book!]! @cacheControl(maxAge: 300)
    myBooks: [Book!]! @cacheControl(maxAge: 30, scope: PRIVATE)
}
~~~

Directive arguments can use valid scalar, enum, list, or input object types. They enable directives to express structured metadata.

Declaring a directive only establishes a contract in the schema. The runtime must have a component that understands and enforces the directive's meaning if the directive needs to alter execution behavior.

## 3. Common Built-in Directives

GraphQL defines several standard directives. Their semantics are already understood by the GraphQL runtime and tools.

### 3.1. @include — Include a Field Only When Condition Is True

`@include(if: Boolean!)` allows a field or fragment to execute when the conditional expression is `true`.

~~~graphql
query GetBook($id: ID!, $showAuthor: Boolean!) {
    book(id: $id) {
        id
        title
        author @include(if: $showAuthor) {
            id
            name
        }
    }
}
~~~

Variables:

~~~json
{
    "id": "book-42",
    "showAuthor": true
}
~~~

When `showAuthor` is `true`, the response can include the `author` field. When `false`, GraphQL skips that field for that execution.

This directive is useful when a UI has optional data sections or when a client wants to reuse a single operation across multiple display states.

### 3.2. @skip — Skip a Field When Condition Is True

`@skip(if: Boolean!)` has the opposite semantics of `@include`: the field or fragment is skipped when the condition is `true`.

~~~graphql
query GetBook($id: ID!, $hideReviews: Boolean!) {
    book(id: $id) {
        title
        reviews(first: 5) @skip(if: $hideReviews) {
            rating
            comment
        }
    }
}
~~~

When `hideReviews` is `true`, the `reviews` field is not executed. When `false`, the field is processed normally.

Both directives can be used in the same operation, though conditions should be kept simple so clients can understand and test them easily.

### 3.3. @deprecated — Mark Legacy Schema Elements

`@deprecated` marks a field, argument, input field, or enum value as no longer recommended.

~~~graphql
type Book {
    id: ID!
    title: String!
    name: String @deprecated(reason: "Use title instead")
}
~~~

In this example, clients should migrate from `name` to `title`. The deprecation reason can be displayed by IDEs or introspection tools.

This directive supports safe schema evolution:

1. Add the new field or argument.
2. Mark the old element with `@deprecated` and provide a specific reason.
3. Update clients to use the new element.
4. Monitor usage of the old element.
5. Remove the old element only after verifying client impact.

`@deprecated` neither deletes the field automatically nor blocks clients from continuing to query it. It is metadata communicating API status.

### 3.4. @specifiedBy — Document Custom Scalar Format

`@specifiedBy(url: String!)` attaches a URL describing the representation rules for a custom scalar:

~~~graphql
scalar UUID @specifiedBy(url: "https://www.rfc-editor.org/rfc/rfc9562")

scalar DateTime @specifiedBy(url: "https://www.rfc-editor.org/rfc/rfc3339")
~~~

The URL should point to an authoritative specification document that accurately describes the format accepted by the scalar.

This directive helps tools and schema consumers understand the scalar's conventions. It does not implement a parser, validator, or serializer on its own. The application must still register the corresponding coercing implementation.

### 3.5. Standard Directives vs. Custom Directives

Directives like `@include`, `@skip`, and `@deprecated` have standardized semantics. GraphQL runtimes and tools know how to handle them.

An application-defined directive such as `@requiresRole` does not gain behavior merely by appearing in SDL. The application must implement a mechanism to read the metadata and enforce the corresponding policy.

This is especially important for authorization: a directive name that sounds like it protects a field does not mean the field is actually protected.

## 4. Custom Directives for Authorization

A schema can publish access policies using custom directives. For example:

~~~graphql
enum Role {
    USER
    EDITOR
    ADMIN
}

directive @requiresRole(role: Role!) on FIELD_DEFINITION

type Report {
    id: ID!
    title: String!
}

type Query {
    publicReport: Report
    editorReport: Report @requiresRole(role: EDITOR)
    adminReport: Report @requiresRole(role: ADMIN)
}
~~~

`@requiresRole` attaches metadata about the role required to invoke the field. This lets schema readers see the access policy right where the field is declared.

However, GraphQL does not treat `@requiresRole` as a security rule automatically. If the application only declares the directive in SDL without a runtime implementation, a client can still call `adminReport` if the field is exposed and the resolver does not check permissions.

Two common approaches exist:

- Use the directive as metadata and integrate it with the application's authorization mechanism, such as via GraphQL Java schema wiring or a DataFetcher wrapper.
- Use Spring Security method security on controllers or services to enforce permissions where data is processed; the directive can be retained as schema documentation if desired.

In Spring for GraphQL applications, Spring Security method security is usually the most direct way to protect resolvers and services. Custom directives can add a centralized policy description layer, provided metadata and enforcement stay strictly synchronized.

### 4.1. Directives Do Not Replace Enforcement Authorization

Do not treat any of the following as security measures:

- Naming a field `adminOnlyData` without checking permissions.
- Annotating a field with a custom directive without implementing directive handling.
- Hiding a field in the GraphiQL UI while leaving the resolver accessible.
- Using `@skip` or `@include` to decide who is allowed to view data.
- Checking permissions only on the client or frontend UI.

Clients can send GraphQL operations directly, bypassing the UI. Therefore, the server must verify identity and permissions whenever data is accessed.

## 5. Authentication and Authorization in Spring for GraphQL

Two concepts must be distinguished:

- **Authentication:** identifying who sent the request.
- **Authorization:** deciding what actions that caller is allowed to perform or what data they may access.

Spring Security typically handles authentication at the web or security filter chain layer. Once a request is authenticated, user identity and authorities are available during GraphQL controller and service invocations.

A GraphQL application can enforce protection at multiple levels:

- Endpoint and transport.
- Root fields in Query or Mutation.
- Nested fields on objects.
- Business actions in services.
- Individual records or specific resources.

Do not protect only the GraphQL endpoint with authentication and assume every field is safe. An authenticated user may still not be authorized to view a particular field or object.

## 6. Enabling Method Security in Spring

Spring Security supports method security through annotations such as `@PreAuthorize`. The application must enable method security in configuration.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Once method security is enabled, Spring evaluates authorization expressions before invoking protected methods.

Example protecting a Query:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

@Controller
class ReportController {

    private final ReportService reportService;

    ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('REPORT_READ')")
    public Report publicReport() {
        return reportService.getPublicReport();
    }

    @QueryMapping
    @PreAuthorize("hasRole('ADMIN')")
    public Report adminReport() {
        return reportService.getAdminReport();
    }
}
~~~

In this example:

- `hasAuthority('REPORT_READ')` requires the user to hold the exact authority `REPORT_READ`.
- `hasRole('ADMIN')` typically checks for the authority prefixed with `ROLE_`, meaning `ROLE_ADMIN` by default.
- If the condition is not satisfied, Spring Security denies the method invocation.

The annotations must be placed on Spring-managed beans. Controllers are discovered and managed as beans by Spring for GraphQL, so method security applies when the GraphQL runtime invokes methods through the Spring proxy.

### 6.1. Distinguishing hasRole and hasAuthority

These two expressions are not identical:

| Expression | Rule |
| --- | --- |
| `hasRole('ADMIN')` | Checks the role with the default `ROLE_` prefix |
| `hasAuthority('REPORT_READ')` | Checks the exact authority `REPORT_READ` |

If your system uses action-based permissions like `BOOK_READ`, `BOOK_UPDATE`, and `REPORT_EXPORT`, `hasAuthority` is usually clearer.

If your system is organized around roles like `ROLE_ADMIN` or `ROLE_EDITOR`, `hasRole` can be easier to read. Standardize naming and permission mapping from your identity provider or authentication provider.

### 6.2. Protecting Mutations

Mutations usually modify state, so they require appropriate permission checks:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

@Controller
class BookMutationController {

    private final BookService bookService;

    BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    @PreAuthorize("hasAuthority('BOOK_CREATE')")
    public Book createBook(@Argument("input") CreateBookInput input) {
        return bookService.create(input);
    }

    @MutationMapping
    @PreAuthorize("hasAuthority('BOOK_ARCHIVE')")
    public Book archiveBook(@Argument("id") UUID id) {
        return bookService.archive(id);
    }
}
~~~

Avoid sharing a single overly broad permission across all mutations if the actions carry different levels of risk. Separating permissions per action makes policies easier to audit and test.

## 7. Object-Level Authorization

Checking roles or authorities only answers whether a user may perform a class of actions. Many business rules also require checking permissions on each individual object.

For example, users may have permission to read books in general, yet only be allowed to view drafts they created themselves. In that case, check both the user's identity and the book's owner.

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;

@Service
class BookService {

    private final BookRepository bookRepository;

    BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @PreAuthorize("@bookAuthorization.canRead(authentication, #id)")
    public Book findReadableById(@P("id") UUID id) {
        return bookRepository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

In this example:

- `@bookAuthorization.canRead(...)` invokes a bean that evaluates object-level access permissions.
- `authentication` is the current authentication object.
- `@P("id")` names the parameter explicitly so the method security expression can reference `#id`.
- The service returns data only if the policy permits it.

Controller calling the service:

~~~java
@QueryMapping
    public Book book(@Argument("id") UUID id) {
    return bookService.findReadableById(id);
}
~~~

Placing checks in the service ensures the rules still apply when the same service is called from a REST endpoint, scheduled job, or another business flow. Still, define the principal and security context clearly for each invocation path.

### 7.1. Do Not Rely Only on Hard-to-Guess IDs

UUIDs or long IDs do not replace authorization. If a client knows or guesses an object's identifier, the server must still verify that the user is authorized to access that object.

This is a fundamental rule to prevent broken object-level authorization (IDOR/BOLA). Every read, update, delete, or share operation on a resource must perform object-level permission checks whenever business rules require it.

## 8. Protecting Nested Fields

GraphQL lets clients traverse data across many field layers. A protected root Query does not automatically make all nested fields safe.

Example schema:

~~~graphql
type Book {
    id: ID!
    title: String!
    internalNotes: String
    author: Author
}

type Author {
    id: ID!
    name: String!
}

type Query {
    book(id: ID!): Book
}
~~~

A user can query:

~~~graphql
query {
    book(id: "book-42") {
        title
        internalNotes
        author {
            name
        }
    }
}
~~~

If `internalNotes` is data meant only for editors, protect that field:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

@Controller
class BookFieldController {

    @SchemaMapping(typeName = "Book", field = "internalNotes")
    @PreAuthorize("hasAuthority('BOOK_INTERNAL_READ')")
    public String internalNotes(Book book) {
        return book.getInternalNotes();
    }
}
~~~

When the GraphQL runtime resolves the `internalNotes` field, Spring Security checks the authority before the method returns data.

Field-level authorization is especially useful when an object contains both public and restricted data. It lets clients query the same object while receiving only the fields the user is permitted to view.

### 8.1. Checking Permissions at the Service/Data Layer

If a field can be reached through multiple resolvers or multiple APIs, do not place the check in only one controller method. Put critical rules in a shared service or policy component so another call path cannot bypass the check.

Example:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

@Service
class BookDetailsService {

    @PreAuthorize("hasAuthority('BOOK_INTERNAL_READ')")
    public String getInternalNotes(UUID bookId) {
        return repository.findInternalNotes(bookId);
    }
}
~~~

Resolver calling the service:

~~~java
@SchemaMapping(typeName = "Book", field = "internalNotes")
public String internalNotes(Book book) {
    return bookDetailsService.getInternalNotes(book.id());
}
~~~

## 9. Combining Custom Directives and Spring Security

If you want access policies visible directly in the schema, you can keep a custom directive as metadata:

~~~graphql
enum Permission {
    BOOK_READ
    BOOK_INTERNAL_READ
    BOOK_UPDATE
    REPORT_ADMIN
}

directive @requiresPermission(permission: Permission!)
    on FIELD_DEFINITION

type Book {
    id: ID!
    title: String!
    internalNotes: String
        @requiresPermission(permission: BOOK_INTERNAL_READ)
}

type Query {
    book(id: ID!): Book
        @requiresPermission(permission: BOOK_READ)
}
~~~

The schema shows which field requires which permission. However, the application must still connect this metadata to an authorization check mechanism.

One GraphQL Java-level approach is using schema directive wiring to read the directive argument and wrap the corresponding DataFetcher with authorization logic. Another approach uses a DataFetcher factory or instrumentation to enforce policies centrally. In Spring for GraphQL, you can connect runtime wiring via extension points such as `RuntimeWiringConfigurer`.

If the application already uses Spring Security method security, make sure the custom directive and annotations do not describe two diverging policies. Pick a single authoritative policy source and derive checks or documentation from it, avoiding two independent role sets.

### 9.1. Directive Metadata Does Not Automatically Invoke Spring Security

Defining:

~~~graphql
type Query {
    adminReport: Report @requiresPermission(permission: REPORT_ADMIN)
}
~~~

is not equivalent to:

~~~java
@PreAuthorize("hasAuthority('REPORT_ADMIN')")
~~~

The SDL line only stores directive information in the schema. The Spring Security annotation is what actually triggers method authorization when the method is called, provided method security is enabled and the bean is invoked through the appropriate proxy.

If you want the directive itself to enforce access, you must write and register runtime handling. Test that an unauthorized user is actually rejected, rather than only checking that the directive appears in the schema.

## 10. Authorization with DataLoader and Batch Fields

In GraphQL, DataLoader or `@BatchMapping` can load multiple related objects in a single batch. This reduces N+1 queries, but does not remove authorization requirements.

For example, a `books` field returns multiple books and each book has a nested `internalNotes` field. If the data is loaded via a batch loader, ensure the batch loader enforces the same permission policy as a single-item resolver.

Principles to maintain:

- Do not share a DataLoader cache across users or tenants if results depend on caller permissions.
- Ensure DataLoaders are created or scoped per appropriate request context.
- Apply tenant and user scoping inside batch queries.
- Never assume that because a root field checked permissions, every record in a batch is permitted to be returned.
- Check permissions before placing sensitive data into a cache that could be read by multiple fields in the same request.

If the same UUID is requested by two users with different permissions, result caches must not be shared across those two security contexts. An improperly scoped cache can leak data even when the initial resolver checked permissions correctly.

## 11. Introspection and Authorization

GraphQL introspection lets clients discover the schema via special fields such as `__schema` and `__type`. It helps IDEs learn the types, fields, arguments, directives, and descriptions published by the API.

Example querying a type name:

~~~graphql
query InspectBookType {
    __type(name: "Book") {
        name
        fields {
            name
            type {
                name
                kind
            }
        }
    }
}
~~~

Introspection is useful for development and client integration. However, hiding the schema does not replace authorization:

- Clients may already know field names from documentation or past requests.
- A field hidden from discovery tools can still be invoked if the server does not block execution.
- Custom directive authorization only provides security if the runtime actually enforces it.

Some systems restrict introspection in production to reduce public schema information. That is a decision about the API discovery surface, not a data access control mechanism. Sensitive resolvers still require independent authorization.

## 12. Handling Authorization Errors in GraphQL

When Spring Security rejects a method invocation, the security exception can be translated into a GraphQL error in the response. GraphQL can return partial data if one field fails while other fields still execute.

Illustrative response:

~~~json
{
    "data": {
        "book": {
            "title": "Spring GraphQL",
            "internalNotes": null
        }
    },
    "errors": [
        {
            "message": "Access is denied",
            "path": ["book", "internalNotes"]
        }
    ]
}
~~~

Actual messages and HTTP status codes depend on your application's transport and error-handling configuration. Do not assume every authorization error turns the entire GraphQL response into HTTP 403 or 500.

Several principles:

- Return messages clear enough for clients without revealing internal permissions or sensitive data structures.
- Do not distinguish too specifically between "object does not exist" and "user lacks permission" if that facilitates resource enumeration.
- Log in a controlled manner with request ID, appropriate principal, and field path.
- Preserve GraphQL partial-data semantics where appropriate.
- Test null propagation if a denied field has a non-null type.

If a sensitive field is declared non-null, a resolver throwing an error can cause null to propagate up to parent fields according to GraphQL rules. Therefore, nullability should reflect both the possibility of absent data and expected error behavior.

## 13. Testing Authorization

Authorization must be tested through actual GraphQL operations, not merely by checking that annotations are present on methods.

In Spring GraphQL, use `GraphQlTester` or a transport-specific tester to execute operations. Tests should verify at least these scenarios:

| Caller | Action | Expected Result |
| --- | --- | --- |
| Unauthenticated | Query requiring login | Denied |
| Regular user | Read public field | Succeeds |
| Regular user | Read internal field | Denied |
| Editor | Read editorial field | Succeeds |
| Non-owner user | Read private record | Denied |
| Admin | Perform admin action | Succeeds |
| Regular user | Perform admin mutation | Denied |

Example testing a denied field:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-42") {
                title
                internalNotes
            }
        }
        """)
        .execute()
        .errors()
        .verify();
~~~

This test must run with a security context for a user lacking the `BOOK_INTERNAL_READ` authority. Without configuring a suitable principal or authentication, the test may be verifying a different case than intended.

### 13.1. Testing Indirect Access Paths Too

A field can appear in multiple operations, fragments, or nested paths. Verify:

- Accessing the field via a root Query.
- Accessing the field via a nested object.
- Accessing the same field using an alias.
- Accessing the field through a fragment.
- Accessing data through a batch loader.
- Calling the same service from another resolver.
- A user holding a role but lacking permission on a specific object.

Aliases and fragments do not create a new authorization mechanism. They only change how the operation selects fields; the server must still protect fields and data along every execution path.

## 14. Common Pitfalls

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| Custom directive appears yet field remains accessible | Directive is only declared with no runtime enforcement | Wrap DataFetcher or use method/service security |
| `@PreAuthorize` has no effect | Method security is not enabled or method is not called through a Spring proxy | Check `@EnableMethodSecurity` and how the bean is invoked |
| User with role still cannot read | Confused `hasAuthority`/`hasRole` or authority mismatch | Check permission mapping and the `ROLE_` prefix |
| Root Query is protected yet nested field leaks | Permission checked only in root resolver | Protect nested fields or services returning sensitive data |
| User can read another user's records | Checked role only without object-level permissions | Apply object-level authorization |
| Data leaks via DataLoader cache | Cache shared across security contexts or missing tenant scope | Scope caches per request and enforce permissions in batching |
| Hid introspection yet field can still be called | Confused schema discoverability with authorization | Protect resolvers independently |
| Authorization error wipes out too much data | Non-null field triggers null propagation | Review nullability and error design |
| Directive and annotation describe conflicting policies | Maintaining two unsynchronized policy sources | Choose a primary policy source and test consistency |

## 15. Workflow for Designing Directives and Authorization

When adding a directive or protecting a GraphQL field, follow this sequence:

1. **Define the directive's purpose.** Does the directive control an operation, describe metadata, or represent a policy?
2. **Choose valid locations.** Declare the directive for the exact locations where it should apply.
3. **Separate metadata from enforcement.** Identify which runtime component actually enforces the rule.
4. **Identify principal and permissions.** Which Spring Security setup, identity provider, or policy service supplies authorities?
5. **Protect at the right layer.** Use method security on resolvers/services and perform object-level checks when needed.
6. **Review nested fields and batch loading.** Ensure no indirect access path bypasses the policy.
7. **Handle errors cleanly.** Do not expose sensitive data or internal details in GraphQL errors.
8. **Test per principal.** Test unauthenticated callers, regular users, editors, and admins.
9. **Verify introspection.** Choose a schema discovery level appropriate for the environment, never as a substitute for authorization.
10. **Monitor and audit policies.** When adding new fields or mutations, verify corresponding permissions before release.

## 16. Summary

Directives add instructions or metadata to GraphQL operations and schemas. Built-in directives such as `@include`, `@skip`, `@deprecated`, and `@specifiedBy` have standardized meanings. Custom directives such as `@requiresRole` or `@requiresPermission` can express access policies directly in SDL, but only provide security enforcement when the application implements runtime enforcement.

In Spring for GraphQL, Spring Security method security with `@PreAuthorize` can protect Queries, Mutations, nested fields, and services. Authorization must consider authorities, roles, and per-object permissions; access paths through fragments, aliases, or DataLoaders must still follow the same policy. Introspection aids schema discovery, not permission checks. Combining clear directives, server-side enforcement, and per-principal tests keeps a GraphQL API secure and maintainable as it evolves.
