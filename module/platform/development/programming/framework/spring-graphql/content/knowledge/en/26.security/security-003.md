# Authorization in controllers in Spring for GraphQL

GraphQL typically provides a single HTTP endpoint, yet that endpoint can execute many queries, mutations, and nested fields with varying sensitivity levels. Therefore, authenticating requests at `/graphql` alone is not enough to protect individual operations. Spring for GraphQL allows combining annotated controllers with Spring Security method security to check permissions directly at the methods handling GraphQL fields.

Annotations such as `@QueryMapping`, `@MutationMapping`, `@SchemaMapping`, and `@BatchMapping` determine which method resolves a field in the schema. When method security is enabled, you can place `@PreAuthorize` on those very methods to restrict who may call the field. This establishes a clear authorization boundary at the GraphQL controller layer, while services still need to enforce business rules if use cases are invoked from multiple other adapters.

After this lesson, you will be able to:

- Distinguish HTTP endpoint authentication from authorization at GraphQL controllers.
- Enable Spring Security method security for annotated controllers.
- Use `@PreAuthorize` on query, mutation, and nested field mappings.
- Check permissions by authority, role, resource ID, and ownership.
- Protect `@BatchMapping` and sensitive fields.
- Understand how authorization exceptions appear in GraphQL responses.
- Test controller authorization using `GraphQlTester` and Spring Security test support.

## 1. Why is authorization needed in controllers?

A single GraphQL HTTP endpoint can serve many fields:

```graphql
type Query {
    books: [Book!]!
    book(id: ID!): Book
    adminReport: AdminReport!
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
    deleteBook(id: ID!): Boolean!
}
```

A user may be allowed to read the book list but not view the admin report or delete books. If `/graphql` is only protected by an `authenticated()` rule, every logged-in user can submit any field exposed by the schema.

Controller authorization binds policy to the method handling each field:

- `books` requires permission to read books.
- `adminReport` requires admin permission.
- `createBook` requires permission to create books.
- `deleteBook` requires permission to delete books.

Clients can submit GraphQL documents directly, set aliases, or use fragments. Hiding a button in the UI is not authorization. The server must verify permissions whenever a field is executed.

## 2. Distinguishing HTTP security and GraphQL field authorization

Spring Security can protect the `/graphql` endpoint at the HTTP layer:

```java
@Configuration
public class HttpSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/graphql").authenticated()
                        .anyRequest().permitAll())
                .build();
    }
}
```

This rule requires the caller to be logged in before the request reaches the GraphQL handler. It does not distinguish which fields are permitted to run inside the GraphQL document.

Controller authorization uses method security:

```java
@QueryMapping
@PreAuthorize("hasAuthority('BOOK_READ')")
public List<BookView> books() {
    return bookService.findAll();
}
```

The two layers serve different purposes:

| Protection layer | Checks | Example |
| --- | --- | --- |
| HTTP Security | Is the request allowed to enter the endpoint? | Users must log in to call `/graphql` |
| Controller method security | Does the caller have permission to invoke a specific field/operation? | Only authority `BOOK_READ` can call `books` |
| Service/domain authorization | Is the caller allowed to act on a specific resource? | Only the owner or an administrator can edit that book |

A system can use all three layers. The endpoint can require general authentication, controllers check field-level permissions, and services check per-resource permissions.

## 3. Enabling method security

For Spring MVC/Servlet applications, enable method security with `@EnableMethodSecurity`:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Once enabled, Spring Security processes annotations such as `@PreAuthorize` and `@PostAuthorize` on Spring beans via proxy/AOP. Spring for GraphQL annotated controllers are also Spring beans, so method security annotations can be placed directly on mapping methods.

For reactive applications using WebFlux and reactive method security, configure `@EnableReactiveMethodSecurity` and keep protected methods returning reactive types such as `Mono` or `Flux`:

```java
@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfiguration {
}
```

Choose the configuration matching your application's web stack and execution model. Do not assume imperative method security configuration automatically substitutes for reactive configuration.

Method security works through proxies. Therefore, protected methods must be invoked through a Spring bean proxy. Avoid self-invocation: a method in the same class directly calling another method on the same instance can bypass the proxy and fail to trigger the security interceptor.

## 4. Protecting Queries with @PreAuthorize

Example controller with a list query and a book detail query:

```java
@Controller
public class BookGraphQlController {

    private final BookService bookService;

    public BookGraphQlController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('BOOK_READ')")
    public List<BookView> books() {
        return bookService.findAll();
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('BOOK_READ')")
    public BookView book(@Argument String id) {
        return bookService.findById(id);
    }
}
```

`@QueryMapping` maps the method to the field of the same name on the root `Query` type. `@PreAuthorize` is evaluated before the method runs. If the caller lacks the `BOOK_READ` authority, Spring Security rejects the call and the method body does not execute.

You can specify an explicit mapping name if the Java method name differs from the GraphQL field name:

```java
@QueryMapping(name = "book")
@PreAuthorize("hasAuthority('BOOK_READ')")
public BookView findBook(@Argument("id") String bookId) {
    return bookService.findById(bookId);
}
```

Authorization is attached to the resolver method, so it still applies when clients invoke the field via an alias or fragment. An alias only changes the response key; it does not create an alternate call path that bypasses method security.

## 5. Protecting Mutations

Mutations change state, so they typically require dedicated authorities:

```java
@MutationMapping
@PreAuthorize("hasAuthority('BOOK_CREATE')")
public BookView createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(toCommand(input));
}

@MutationMapping
@PreAuthorize("hasAuthority('BOOK_DELETE')")
public boolean deleteBook(@Argument String id) {
    bookService.delete(id);
    return true;
}
```

Someone with `BOOK_READ` does not implicitly have `BOOK_CREATE` or `BOOK_DELETE`. Separating authorities by action keeps policies clear and easy to test.

Method security runs when the field resolver is called. GraphQL executes top-level mutation fields sequentially within an operation, yet each field must still check permissions on its own. Do not assume the caller is authorized to execute the second field just because the first field was allowed.

## 6. Protecting nested fields with @SchemaMapping

Authorization does not apply only to root queries/mutations. An object may contain sensitive fields that only certain user groups are allowed to view:

```graphql
type Book {
    id: ID!
    title: String!
    internalNotes: String
}
```

The `internalNotes` field resolver can be protected separately:

```java
@Controller
public class BookFieldController {

    private final BookAuditService bookAuditService;

    public BookFieldController(BookAuditService bookAuditService) {
        this.bookAuditService = bookAuditService;
    }

    @SchemaMapping(typeName = "Book", field = "internalNotes")
    @PreAuthorize("hasAuthority('BOOK_AUDIT_READ')")
    public String internalNotes(BookView book) {
        return bookAuditService.internalNotes(book.id());
    }
}
```

The caller can read `Book.id` and `Book.title` without having permission to read `internalNotes`. When the sensitive field is selected, method security checks the authority before calling the service.

If a field can be read through multiple paths, ensure every resolver/service providing that data enforces the appropriate policy. Do not rely on the UI hiding the field or the client not knowing the field name.

## 7. Protecting @BatchMapping

`@BatchMapping` handles a field for a group of source objects. Method security can be placed directly on the batch method:

```java
@BatchMapping(typeName = "Book", field = "author")
@PreAuthorize("hasAuthority('BOOK_READ')")
public Map<BookView, AuthorView> author(List<BookView> books) {
    return authorService.findForBooks(books);
}
```

Here, the authority is checked when the batch method is invoked. Because a single call can process multiple source objects, this annotation protects the entire batch invocation. It does not automatically check ownership of each individual book or author.

If permissions depend on tenant, owner, or individual resource state, the service needs to filter/check each source-target pair in the batch. For example, bulk queries must restrict the tenant from the authenticated security context; never take a tenant ID from an untrusted client argument and use it as policy.

If an element is not allowed to be viewed, deciding whether to return null, omit the field, or reject the entire batch must align with the schema and security policy. In particular, avoid returning data for unauthorized resources simply because their IDs appeared in the same batch.

## 8. Checking permissions by authority and role

Spring Security supports checking a specific authority:

```java
@PreAuthorize("hasAuthority('BOOK_READ')")
```

`hasAuthority` performs an exact string comparison against the authority. It fits action-based permissions such as `BOOK_READ`, `BOOK_CREATE`, and `BOOK_AUDIT_READ`.

You can check a role:

```java
@PreAuthorize("hasRole('ADMIN')")
```

`hasRole('ADMIN')` checks for the authority `ROLE_ADMIN` by default because the `ROLE_` prefix is added automatically. If you use `hasAuthority('ADMIN')`, Spring compares against the exact string `ADMIN` without adding a prefix.

Do not mix the two conventions. Define an authority naming convention in the application and apply it consistently across configuration, JWT converters, tests, and annotations.

## 9. Checking permissions by resource ID

Permission to read a resource type does not mean permission to read every resource of that type. For example, a user has `BOOK_READ` but may only read books in their own tenant or books they own.

You can call a policy bean from SpEL:

```java
@Component("bookAuthorization")
public class BookAuthorization {

    private final BookPermissionService permissionService;

    public BookAuthorization(BookPermissionService permissionService) {
        this.permissionService = permissionService;
    }

    public boolean canRead(Authentication authentication, String bookId) {
        return permissionService.canRead(authentication.getName(), bookId);
    }
}
```

Place the policy on the service method:

```java
@Service
public class BookService {

    @PreAuthorize("hasAuthority('BOOK_READ') "
            + "and @bookAuthorization.canRead(authentication, #p0)")
    public BookView findById(String bookId) {
        return bookRepository.findViewById(bookId)
                .orElseThrow(() -> new BookNotFoundException(bookId));
    }
}
```

`#p0` references the first method parameter, avoiding reliance on parameter names preserved in bytecode. You can use `#bookId` if the project ensures parameter name metadata is compiled and Spring can discover those names.

The policy bean should check permissions based on the authenticated identity and server-side data. Do not use a `userId` value sent by the client as proof that the caller is that user.

## 10. Controller policy and service policy

Placing `@PreAuthorize` on a controller has the advantage of making the policy immediately visible at the GraphQL field. However, a service may be called from a REST controller, scheduled job, message consumer, or another use case.

A common structure is:

- The controller checks permission to access a GraphQL field or operation group.
- The service/application layer checks business rules and resource permissions.
- The repository/query always applies the necessary tenant/ownership constraints.

Example of a controller checking operation permission:

```java
@MutationMapping
@PreAuthorize("hasAuthority('BOOK_UPDATE')")
public BookView updateBook(@Argument("input") UpdateBookInput input) {
    return bookService.update(toCommand(input));
}
```

The service checks whether the caller is allowed to edit that specific book:

```java
@PreAuthorize("@bookAuthorization.canEdit(authentication, #p0.bookId())")
@Transactional
public BookView update(UpdateBookCommand command) {
    // Perform the update after the resource policy has been verified.
    return bookRepository.update(command);
}
```

It is not strictly necessary to repeat the exact same permission expression at every layer. Place policies at appropriate boundaries and ensure the use case cannot be invoked through another adapter while bypassing mandatory checks.

## 11. @PostAuthorize and checking returned objects

`@PostAuthorize` checks the result after the method completes. It can be useful when the access decision depends on properties of the newly loaded object:

```java
@PostAuthorize("returnObject == null or "
        + "@bookAuthorization.canRead(authentication, returnObject.id())")
public BookView findVisibleBook(String bookId) {
    return bookRepository.findViewById(bookId).orElse(null);
}
```

For policies that must be checked before reading or before performing side effects, prefer `@PreAuthorize`. `@PostAuthorize` runs after the method, so data has already been loaded and work inside the method has already occurred. Do not use it to protect mutations with side effects if permission must be confirmed before modifying data.

For collections, do not load all data and rely on post-filtering when you can restrict the query upfront by caller/tenant. Filtering at the repository reduces leakage risks via logs, caches, batches, or other processing paths.

## 12. Principal and Authentication in controllers

Method security can use `authentication` in SpEL expressions without passing a principal from the client. When controller logic needs to know the current user to build a command or filter data, retrieve the principal from the Spring Security context or pass a server-created actor snapshot.

Example with an actor placed into `GraphQLContext` by an interceptor:

```java
@QueryMapping
@PreAuthorize("isAuthenticated()")
public List<BookView> myBooks(
        @ContextValue(name = "currentActor") CurrentActor actor) {
    return bookService.findVisibleTo(actor.subject());
}
```

`CurrentActor` must be created by the server from the authenticated `Authentication`. Do not bind an actor-shaped object from GraphQL variables and use it as the principal. If using both method security and an actor context, ensure both sources represent the same authentication context and cannot be overwritten by the client.

## 13. Authorization exceptions in GraphQL responses

If `@PreAuthorize` denies a method invocation, Spring Security throws an exception in the `AccessDeniedException` hierarchy (such as `AuthorizationDeniedException`). When the error arises while GraphQL is resolving a field, Spring for GraphQL can map it to a GraphQL error.

Example handler:

```java
@ControllerAdvice
public class GraphQlAuthorizationExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleAccessDenied(
            AccessDeniedException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.FORBIDDEN)
                .message("You are not allowed to access this field")
                .extensions(Map.of("code", "FORBIDDEN"))
                .build();
    }
}
```

`GraphqlErrorBuilder.newError(environment)` preserves the path and location of the executing field. Clients can determine which field was denied via `errors[].path` and use `extensions.code` to handle it.

If a request is rejected in the Spring Security filter chain before GraphQL execution starts, `@GraphQlExceptionHandler` cannot handle that error; the client may receive HTTP 401/403 at the transport layer. Distinguish endpoint errors from single-field authorization errors.

## 14. Nullability and data when a field is denied

When field authorization fails, GraphQL handles the error according to the field's nullability. For example:

```graphql
type Book {
    id: ID!
    title: String!
    internalNotes: String
}
```

If `internalNotes` is nullable, the error can turn that field into null while `id` and `title` still have data. If the field is declared `String!`, the error can bubble null up to the parent object and onward to the root depending on the nullability of enclosing levels.

Do not change a sensitive field to nullable solely to hide authorization errors. Nullability should reflect the data contract; clients still need to receive a GraphQL error or an explicit policy response. If you want to avoid disclosing whether a resource exists, you can return the same public error for non-existent and unauthorized cases, while keeping semantics consistent.

## 15. Multiple root fields and aliases do not bypass authorization

A query can request multiple root fields at once:

```graphql
query Dashboard {
    visibleBooks: books {
        id
        title
    }
    admin: adminReport {
        totalUsers
    }
}
```

GraphQL may resolve query fields in parallel. Each controller method must enforce its own policy. If `books` is permitted but `adminReport` is denied, the response can retain `visibleBooks` data and include an error for the `admin` branch if nullability allows.

An alias only changes the response key. It does not alter which method is called or the policy attached to the resolver. Fragments also do not create alternate access paths. Authorization must be based on the actual method/resource, not on alias names or query structure chosen by the client.

## 16. Authorization in reactive applications

With WebFlux, the security context is propagated through the Reactor Context. When using reactive method security, protected methods should return `Mono` or `Flux` so the interceptor evaluates permissions within reactive execution:

```java
@Controller
public class ReactiveBookController {

    private final ReactiveBookService bookService;

    public ReactiveBookController(ReactiveBookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('BOOK_READ')")
    public Flux<BookView> books() {
        return bookService.findAll();
    }
}
```

Do not call `.block()` in a controller to obtain a result before checking permissions. Also do not arbitrarily switch to custom executors that cause the Reactor Context to be lost. If a service or batch loader needs the actor, propagate context using the appropriate reactive mechanism and test with real requests.

## 17. Testing authorization in GraphQL controllers

You can use Spring Security Test with `@WithMockUser` to establish authentication in tests:

```java
@Test
@WithMockUser(authorities = "BOOK_READ")
void userWithBookReadCanQueryBooks() {
    graphQlTester.document("""
            query {
                books {
                    id
                    title
                }
            }
            """)
        .execute()
        .path("books")
        .entityList(BookView.class);
}
```

Testing a user lacking the authority:

```java
@Test
@WithMockUser(authorities = "PROFILE_READ")
void userWithoutBookReadIsDenied() {
    graphQlTester.document("""
            query {
                books {
                    id
                }
            }
            """)
        .execute()
        .errors()
        .satisfy(errors -> {
            assertThat(errors).isNotEmpty();
            assertThat(errors.get(0).getMessage())
                    .contains("not allowed");
        });
}
```

For the test to work properly, the test slice must import the method security configuration and the relevant GraphQL controller/service configuration. `@WithMockUser` supplies a mock authority; it does not replace integration tests for the JWT converter, HTTP filter chain, or GraphQL interceptors.

For tests over HTTP, you can use `WebTestClient`/`MockMvc` together with Spring Security test support to send requests with a mock user or JWT. This verifies that requests pass through the security filter chain, transport, and GraphQL execution.

## 18. Cases to test

An authorization test suite for GraphQL should cover:

1. Unauthenticated users are blocked at the endpoint if HTTP policy requires login.
2. Users with `BOOK_READ` can query book-reading fields.
3. Users with only `BOOK_READ` cannot invoke mutations to create or delete books.
4. Users lacking `BOOK_AUDIT_READ` cannot read the `internalNotes` field.
5. Users with a general authority who do not own a resource cannot edit that resource.
6. Aliases and fragments do not change policy enforcement.
7. A query with multiple root fields returns correct partial data when one field is denied.
8. `@BatchMapping` checks permissions for the batch and for each resource per policy.
9. Async/reactive resolvers receive the proper security context.
10. Authorization errors have safe codes, paths, and messages.
11. Services still protect use cases when invoked from adapters other than GraphQL.
12. Non-existent resources and unauthorized resources are handled according to anti-enumeration policy.

## 19. Common issues

- **Using only `authenticated()` for `/graphql`:** logged-in users may still lack permission to call specific fields.
- **Protecting only root queries:** nested fields can contain sensitive data and require their own policies.
- **Assuming hiding fields in the UI is enough:** clients can send queries manually.
- **Placing `@PreAuthorize` without `@EnableMethodSecurity`:** the annotation is not activated.
- **Using the wrong role prefix:** `hasRole('ADMIN')` looks for `ROLE_ADMIN` by default; `hasAuthority` matches exact strings.
- **Using `@PostAuthorize` for side effects:** the method has already run before permissions are checked.
- **Checking only general authorities:** insufficient for permissions scoped by owner, tenant, or resource ID.
- **Using `userId` from variables as identity:** clients can impersonate other users.
- **Skipping authorization in batch loaders:** a batch can contain resources across multiple permission scopes.
- **Self-invocation of protected methods:** internal calls can bypass the Spring proxy.
- **Confusing HTTP 403 with GraphQL field errors:** filter chain errors occur before execution, whereas method security errors may appear in GraphQL `errors`.
- **Not testing through the real transport:** resolver unit tests do not verify JWTs, filter chains, or context propagation.

## 20. Workflow for implementing authorization in controllers

When adding a query, mutation, or field resolver, follow these steps:

1. Determine whether callers must be logged in or if the field can be accessed anonymously.
2. Protect the `/graphql` endpoint at the HTTP layer according to general policy.
3. Enable `@EnableMethodSecurity` or reactive method security as appropriate.
4. Attach `@PreAuthorize` to `@QueryMapping`/`@MutationMapping` methods requiring operation-level policies.
5. Protect sensitive fields on `@SchemaMapping` and `@BatchMapping`.
6. Use authorities/roles consistently; check resource ownership and tenant in service/domain layers.
7. Never trust a principal, user ID, or tenant ID sent by the client.
8. Map access denied to a safe GraphQL error when the error occurs during execution.
9. Design nullability appropriately for fields that may be denied.
10. Test allowed callers, denied callers, resource-level policies, batches, aliases, fragments, and transport.

Controller authorization places permission checks directly on the methods resolving GraphQL fields. `@PreAuthorize` can protect queries, mutations, nested fields, and batch mappings once method security is enabled. Combining controller policies with per-resource permission checks in services helps the API both control which fields clients can request and protect business rules when use cases are called from multiple entry points. By distinguishing HTTP security from GraphQL field authorization and testing both error responses and partial data, Spring for GraphQL can provide a clearer and safer API surface.

## References

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Exception Handling](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.exception-handling)
- [Spring Security Test — Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
