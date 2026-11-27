# Queries and Authorization in Spring for GraphQL

## Objectives

After this lesson, you will be able to:

- Explain why GraphQL Queries still require authentication and authorization even though they only read data.
- Distinguish securing the `/graphql` endpoint from securing individual Query fields.
- Use Spring Security method security to control `@QueryMapping` methods.
- Distinguish `hasRole` and `hasAuthority`.
- Enforce access control per object, owner, and tenant.
- Protect data at nested fields and the service layer.
- Understand the impact of aliases, fragments, multiple root fields, and DataLoader on authorization.
- Handle access errors in GraphQL responses and control partial data.
- Write tests for authorized, unauthorized, and out-of-scope data access.

## 1. Why Do Queries Need Authorization?

GraphQL Queries are typically used for reading data. However, the data read can still be sensitive: personal profiles, order details, internal reports, editorial notes, or data belonging to another tenant.

Authentication and authorization answer two different questions:

- **Authentication:** who is sending the request?
- **Authorization:** which fields or resources is that caller allowed to read?

Example schema:

~~~graphql
type Book {
    id: ID!
    title: String!
    internalNotes: String
}

type Report {
    id: ID!
    name: String!
}

type Query {
    book(id: ID!): Book
    publicCatalog: [Book!]!
    adminReports: [Report!]!
}
~~~

A user may be permitted to view `publicCatalog`, yet not permitted to view `internalNotes` or `adminReports`. Therefore, merely authenticating that the request is logged in is not enough.

Authorization for Queries must be enforced on the server, where resolvers execute or data is accessed. Do not rely on the frontend UI, field names, unimplemented custom directives, or hiding buttons on screen to protect data.

## 2. Two Layers of Protection: Endpoint and Field

A Spring for GraphQL application typically has two related control layers:

1. **Endpoint/transport security:** the Spring Security filter chain determines who can send requests to the GraphQL endpoint, such as `/graphql`.
2. **Field/method authorization:** Spring Security method security checks whether the caller has permission to execute a specific Query or access a specific resource.

These two layers complement each other. The endpoint can require the user to be logged in, while individual Query fields apply finer-grained permissions.

For example, the `/graphql` endpoint only allows authenticated users. Then:

- `publicCatalog` requires authority `BOOK_READ`.
- `adminReports` requires role `ADMIN`.
- `book(id)` requires permission to read the specific book with the given ID.

A single request can contain multiple root fields:

~~~graphql
query Dashboard {
    publicCatalog {
        id
        title
    }
    adminReports {
        id
        name
    }
}
~~~

Each root field is resolved by its own mapping. Just because one field is permitted to run does not mean other fields in the same operation are permitted.

If the application allows anonymous access to certain Queries, you can configure the endpoint to permit requests to reach GraphQL and enforce authentication/authorization per field. If the entire API requires login, the filter chain can require authentication before requests reach the GraphQL runtime. Define clear policies at both layers.

## 3. Enabling Spring Security Method Security

To use `@PreAuthorize`, the application must enable method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Once enabled, Spring Security can evaluate permission expressions before invoking protected methods.

`@PreAuthorize` works through Spring AOP proxies. Methods must be invoked through a Spring-managed bean; calling another method internally on the same object (`self-invocation`) can bypass the proxy and fail to trigger the check as expected.

In the example below, the controller is a Spring bean managed by Spring for GraphQL:

~~~java
@Controller
class BookQueryControllerSimple {

    private final BookService bookService;

    BookQueryControllerSimple(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('BOOK_READ')")
    public Book book(@Argument("id") UUID id) {
        return bookService.findReadableById(id);
    }
}
~~~

When the GraphQL runtime resolves the `Query.book` field, method security checks the `BOOK_READ` authority. If the user lacks permission, the method is not executed and Spring Security denies the call.

## 4. Protecting Queries with @PreAuthorize

`@QueryMapping` maps a controller method to a field on the root `Query` type. You can combine this annotation with `@PreAuthorize` to require permissions before the resolver runs.

Schema:

~~~graphql
type Report {
    id: ID!
    title: String!
}

type Query {
    publicReport: Report
    editorReport: Report
    adminReport: Report
}
~~~

Controller:

~~~java
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Controller;

@Controller
class ReportQueryController {

    private final ReportService reportService;

    ReportQueryController(ReportService reportService) {
        this.reportService = reportService;
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('REPORT_READ')")
    public Report publicReport() {
        return reportService.getPublicReport();
    }

    @QueryMapping
    @PreAuthorize("hasRole('EDITOR')")
    public Report editorReport() {
        return reportService.getEditorReport();
    }

    @QueryMapping
    @PreAuthorize("hasRole('ADMIN')")
    public Report adminReport() {
        return reportService.getAdminReport();
    }
}
~~~

Rules:

- `hasAuthority('REPORT_READ')` checks for an authority named exactly `REPORT_READ`.
- `hasRole('EDITOR')` checks for a role with the default `ROLE_` prefix, i.e., `ROLE_EDITOR`.
- `hasRole('ADMIN')` corresponds to authority `ROLE_ADMIN` under default configuration.

If the application uses action-based permissions such as `BOOK_READ`, `BOOK_EXPORT`, or `REPORT_READ`, `hasAuthority` usually expresses the policy clearly. If the system is organized around roles such as `ROLE_EDITOR` and `ROLE_ADMIN`, `hasRole` can be easier to read.

Do not use a single `ADMIN` permission for every operation if actions vary in sensitivity. Purpose-based permissions make policies easier to audit and test.

## 5. Distinguishing hasRole and hasAuthority

These two expressions are frequently confused:

| Expression | How it checks | Example authority |
| --- | --- | --- |
| `hasRole('ADMIN')` | Prepends default role prefix `ROLE_` | `ROLE_ADMIN` |
| `hasAuthority('BOOK_READ')` | Compares exact authority | `BOOK_READ` |

Example:

~~~java
@QueryMapping
@PreAuthorize("hasRole('ADMIN')")
public List<Report> adminReports() {
    return reportService.findAll();
}
~~~

If the principal only holds authority `ADMIN` without `ROLE_ADMIN`, `hasRole('ADMIN')` may not match. You can customize the role prefix, but keep the convention consistent across the entire system.

Do not mix `ROLE_ADMIN`, `ADMIN`, and `BOOK_ADMIN` arbitrarily. Define roles clearly as user groups, and authorities as specific permissions that resolvers or services check.

## 6. Object-Level Authorization

Having a general authority to read books does not necessarily mean being allowed to read every book. A user might only be permitted to view books they created, or only access data belonging to their tenant.

For example, a Query accepting an ID:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Controller:

~~~java
import org.springframework.security.core.parameters.P;
import org.springframework.security.core.Authentication;

@Controller
class BookQueryControllerWithObjectPolicy {

    private final BookService bookService;

    BookQueryControllerWithObjectPolicy(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    @PreAuthorize("@bookAuthorization.canRead(authentication, #id)")
    public Book book(@Argument("id") @P("id") UUID id) {
        return bookService.findById(id);
    }
}
~~~

`@bookAuthorization.canRead(authentication, #id)` calls a policy bean to check whether the current user is allowed to read the book with that ID. `@P("id")` provides an explicit parameter name for the method security expression; you can also configure compilation to preserve parameter names if the project relies on parameter name metadata.

Example policy bean:

~~~java
import org.springframework.security.core.Authentication;

@Component("bookAuthorization")
class BookAuthorization {

    private final BookRepository bookRepository;

    BookAuthorization(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    public boolean canRead(Authentication authentication, UUID id) {
        return bookRepository.existsReadableByIdAndUsername(
                id,
                authentication.getName()
        );
    }
}
~~~

The `existsReadableByIdAndUsername` method here represents a permission-checking query according to the application's data model. Adjust repository method names and ownership rules to fit your real domain.

For sensitive data, it can be safer and more efficient to scope the query by principal directly in the repository, rather than loading an arbitrary object and checking permission afterward. Avoid letting the client supply `ownerId` or `tenantId` and treating that value as proof of authorization.

## 7. Tenant-Based Authorization

In multi-tenant systems, the same ID can point to data belonging to a specific tenant. Users may only access data within the tenant scope derived from their authenticated identity.

Example service obtaining the tenant from the principal or a component providing current user details:

~~~java
@Service
class BookQueryService {

    private final BookRepository bookRepository;
    private final CurrentUser currentUser;

    BookQueryService(
            BookRepository bookRepository,
            CurrentUser currentUser) {
        this.bookRepository = bookRepository;
        this.currentUser = currentUser;
    }

    public Book findVisibleById(UUID id) {
        UUID tenantId = currentUser.tenantId();

        return bookRepository.findByIdAndTenantId(id, tenantId)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

In this example, `tenantId` comes from `CurrentUser`, which is built from the security context. It does not come from an argument sent by the client.

If an API has a Query that takes `tenantId` for business reasons, the server must still verify that the user has permission to access that tenant. Never use the argument value as the sole basis for scoping data.

Scoping by tenant directly in the data query reduces the risk of accidentally returning the wrong record. For read operations, you can return the same "not found" outcome for both non-existent records and out-of-scope records if policy requires avoiding resource existence disclosure.

## 8. Placing Authorization in Controllers or Services?

You can protect a Query right at the controller:

~~~java
@QueryMapping
@PreAuthorize("hasAuthority('BOOK_READ')")
public List<Book> books() {
    return bookService.findAllVisibleToCurrentUser();
}
~~~

This makes it obvious which Query field requires which permission. However, the same service may be called from another resolver, a REST API, or another business flow. If protection exists only in the controller, other call paths can bypass the policy.

For critical business rules, place authorization in the shared service or data access layer:

~~~java
@Service
class BookQueryService {

    @PreAuthorize("hasAuthority('BOOK_READ')")
    public List<Book> findAllVisibleToCurrentUser() {
        return repository.findAllVisibleToCurrentUser();
    }
}
~~~

Controller calling the service:

~~~java
@QueryMapping
public List<Book> books() {
    return bookQueryService.findAllVisibleToCurrentUser();
}
~~~

You can protect both layers when there is a clear reason: the controller expresses the GraphQL field policy, while the service guards shared business logic. Avoid duplicating annotations without a clear convention, as that makes it confusing where the true policy source lives.

## 9. Protecting the Root Query Does Not Automatically Protect All Nested Fields

GraphQL allows clients to query objects across multiple levels:

~~~graphql
query {
    book(id: "book-42") {
        title
        internalNotes
        author {
            name
            privateEmail
        }
    }
}
~~~

Suppose `book(id)` requires `BOOK_READ`, while `internalNotes` and `privateEmail` are restricted data. Permission to read the root object does not imply the user can read every child field.

Check permissions on nested resolvers or services that supply sensitive data:

~~~java
@Controller
class BookDetailsController {

    private final BookDetailsService detailsService;

    BookDetailsController(BookDetailsService detailsService) {
        this.detailsService = detailsService;
    }

    @SchemaMapping(typeName = "Book", field = "internalNotes")
    @PreAuthorize("hasAuthority('BOOK_INTERNAL_READ')")
    public String internalNotes(Book book) {
        return detailsService.getInternalNotes(book.id());
    }
}
~~~

If a field can be reached from multiple places, consider protecting it in the service as well. The key rule is that every path to sensitive data must pass through effective authorization checks.

## 10. Aliases, Fragments, and Multiple Root Fields Do Not Bypass Authorization

A GraphQL operation can use aliases to call the same field multiple times:

~~~graphql
query CompareBooks {
    first: book(id: "book-1") {
        title
    }
    second: book(id: "book-2") {
        title
    }
}
~~~

Clients can also use fragments:

~~~graphql
fragment BookSummary on Book {
    id
    title
}

query {
    book(id: "book-42") {
        ...BookSummary
    }
}
~~~

Aliases and fragments only change how the client structures the selection set. They do not alter resolver security rules. If the `book` method has `@PreAuthorize`, every execution of that field goes through the corresponding check.

Similarly, an operation can request multiple root fields. Each resolver must enforce its own field policy; never assume that because one field is allowed, the entire operation is allowed.

## 11. DataLoader and Access Scope

DataLoader batches related data fetches to reduce N+1 queries. However, batch loading does not remove authorization requirements.

For example, multiple books request author data together. The batch loader must scope results by the same security context and tenant scope as single-item queries.

Principles:

- Create and use DataLoaders within request scope using Spring GraphQL's mechanisms.
- Never share cached results across users or tenants when data depends on permissions.
- Include tenant/user scope in batch queries when results must be restricted by principal.
- Do not assume that because the root Query checked permissions, every item in a batch is permitted to be returned.
- Check permissions before sensitive data is placed into a cache reusable within the request.

If the same ID is requested by two principals with different permissions, cached results must not be shared across security contexts. Improperly scoped caches can leak data even when individual resolvers check permissions correctly.

## 12. Handling Authorization Errors in GraphQL

When method security denies a call, Spring Security can throw `AccessDeniedException`. The exception is processed through the application's GraphQL error handling mechanism, such as `DataFetcherExceptionResolver` or `@GraphQlExceptionHandler`.

An illustrative response when a field is denied:

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
            "message": "You do not have permission to access this field",
            "path": ["book", "internalNotes"]
        }
    ]
}
~~~

GraphQL can return partial data: one field fails while other fields succeed. The actual HTTP status depends on whether the request was blocked in the filter chain or the error occurred during GraphQL execution. Do not assume every authorization error turns the entire response into HTTP 403.

Points to note:

- Use client-appropriate messages without revealing internal roles, database queries, or sensitive data.
- Log selectively with request ID, principal, and field path when needed for investigation.
- Distinguish unauthenticated errors from authenticated-but-unauthorized errors.
- If a denied field is non-null, the error can propagate up to the parent field according to GraphQL null propagation rules.
- Do not return details that let callers probe whether a resource exists if policy requires hiding existence.

How exceptions map and errors are classified depends on the application's Spring GraphQL configuration. Verify actual responses with integration tests rather than assuming a fixed HTTP status.

## 13. Asynchronous Queries and SecurityContext

A resolver can return synchronous types or asynchronous types such as `CompletableFuture`, `Mono`, or `Flux`. When using reactive types, ensure the security context propagates properly through execution.

For reactive applications, enable reactive method security with the appropriate Spring Security configuration, such as `@EnableReactiveMethodSecurity`, and access the principal using Reactor Context-based mechanisms. Do not read thread-local `SecurityContextHolder` in a reactive flow assuming the context always exists on the current thread.

For servlet applications and synchronous methods, `@EnableMethodSecurity` with `@PreAuthorize` is generally the right setup. If a resolver offloads work to a separate executor or callback, ensure context propagation is configured properly.

General rule: authorization must be evaluated within the exact security context of the current request, even when resolvers execute asynchronously.

## 14. Testing Query Authorization

Authorization should be tested through real GraphQL operations. Do not merely verify that an annotation exists on a method; test that authorized and unauthorized users receive different expected results.

For method security, you can use `ExecutionGraphQlServiceTester` to test GraphQL execution directly on the test thread. This works well when using `@WithMockUser` to supply a security context for synchronous resolver calls:

~~~java
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class BookQuerySecurityTests {

    @Autowired
    ExecutionGraphQlService executionGraphQlService;

    GraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        graphQlTester = ExecutionGraphQlServiceTester.create(
                executionGraphQlService
        );
    }

    @Test
    @WithMockUser(authorities = "BOOK_READ")
    void readerCanReadBook() {
        graphQlTester.document("""
                query {
                    book(id: "book-42") {
                        title
                    }
                }
                """)
                .execute()
                .path("book.title")
                .entity(String.class)
                .isEqualTo("Spring GraphQL");
    }

    @Test
    @WithMockUser(authorities = "BOOK_WRITE")
    void writerWithoutReadPermissionIsDenied() {
        graphQlTester.document("""
                query {
                    book(id: "book-42") {
                        title
                    }
                }
                """)
                .execute()
                .errors()
                .verify();
    }
}
~~~

This example assumes the application has method security configured and matching sample data. Add the Spring Security Test dependency to use `@WithMockUser`. `@WithMockUser` sets the security context on the test thread; therefore, this example focuses on direct execution and synchronous resolvers.

When you need to test endpoint authentication and the web security filter chain, use `HttpGraphQlTester` or `WebGraphQlTester` over HTTP and supply credentials in the request itself (such as Basic or Bearer tokens per your test setup). `@WithMockUser` on a test method does not automatically propagate the principal to a real HTTP request running on another server thread. Execution service tester also does not test endpoint protection rules because it bypasses the web filter chain.

### 14.1. Recommended Test Matrix

| Principal | Query | Expected Result |
| --- | --- | --- |
| Unauthenticated | Query requiring login | Rejected by filter chain |
| User with `BOOK_READ` | Read book within scope | Succeeds |
| User with only `BOOK_WRITE` | Read book | Denied |
| User with read permission but different owner | Read private record | Denied or not found per policy |
| User in tenant A | Read tenant B record | Does not return tenant B data |
| Editor | Read editorial field | Succeeds |
| Regular user | Read editorial field | Denied |
| User authorized for one root field | Also calls an admin root field | Only the permitted field succeeds |

Also test aliases, fragments, nested fields, and DataLoader to verify no access path bypasses the policy.

## 15. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Logged-in user can still read sensitive fields | Only the endpoint is protected, not resolvers or services | Add method/object-level authorization |
| `@PreAuthorize` has no effect | Method security is not enabled or call bypasses Spring proxy | Check `@EnableMethodSecurity`, beans, and self-invocation |
| `hasRole('ADMIN')` does not match | Principal has `ADMIN` instead of `ROLE_ADMIN` | Align role prefix or use the appropriate authority |
| User with `BOOK_READ` reads another tenant's record | Only authority is checked, data is not scoped by tenant | Derive tenant from principal and filter in repository |
| Root Query is protected but nested field leaks | Permission placed only on root resolver | Protect nested resolvers or data-providing services |
| Alias/fragment opens unexpected access path | Only one specific operation was tested | Test the same field across multiple selection sets |
| DataLoader returns another principal's data | Cache does not match request/security scope | Scope cache by request and tenant |
| Tests always pass even when user lacks permission | Test lacks security context or bypasses proxy/filter chain | Use `@WithMockUser` and the appropriate `GraphQlTester` |
| Failing field wipes out parent data | Non-null propagation | Review nullability and how authorization errors are mapped |

## 16. Workflow for Designing Query Authorization

When adding a new Query, you can follow this sequence:

1. **Determine data sensitivity.** Is the field public, authenticated-only, or restricted to a specific group of users?
2. **Identify the principal.** From which security context are user, tenant, and permissions obtained?
3. **Protect the endpoint appropriately.** Decide whether `/graphql` permits anonymous access or requires authentication.
4. **Protect the resolver.** Use `@PreAuthorize` or the corresponding method security mechanism on the root Query.
5. **Check object-level permissions.** Verify owner, tenant, and access relationships when the field accepts an ID.
6. **Scope data queries.** Push permission boundaries into the repository/query where appropriate.
7. **Review nested fields and batch loaders.** Ensure child fields and caches never return unauthorized data.
8. **Design errors.** Distinguish unauthenticated, unauthorized, and not-found cases per your published policy.
9. **Test across principals.** Include regular users, editors, admins, owners, and users from other tenants.
10. **Track schema changes.** Review permissions for every new Query before releasing it.

## 17. Summary

GraphQL Queries only read data, yet they can still expose sensitive information. Spring Security can protect the GraphQL endpoint at the transport layer and protect individual `@QueryMapping` methods using method security such as `@PreAuthorize`. `hasRole` checks roles with the default prefix, whereas `hasAuthority` checks specific authorities.

Authorization must account for both action permissions and per-object permissions. For multi-tenant data, obtain the tenant from the security context and scope queries on the server. Protecting a root Query does not automatically protect all nested fields; aliases, fragments, and DataLoaders must adhere to the same policy. Testing real GraphQL operations across multiple principals verifies that data is returned only to authorized callers.
