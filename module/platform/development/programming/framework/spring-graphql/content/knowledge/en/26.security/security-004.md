# Method security in Spring for GraphQL

## Objectives

After this lesson, you will be able to:

- Explain method security and its role alongside HTTP request security.
- Enable method security with `@EnableMethodSecurity`.
- Use `@PreAuthorize` to check permissions before a method runs.
- Use `@PostAuthorize` to check the return value when appropriate.
- Distinguish roles from authorities in security expressions.
- Protect Queries, Mutations, and nested fields using service methods.
- Check object access permissions by owner or tenant to prevent IDOR.
- Understand the limitations of Spring AOP proxies and self-invocation bugs.
- Distinguish imperative method security from reactive method security.
- Map access-denied errors to safe GraphQL errors.
- Test access permissions with `@WithMockUser` and `GraphQlTester`.

## 1. What is method security?

Method security is a mechanism for checking permissions directly at the method invocation boundary of a Spring bean. Instead of only authenticating or authorizing an HTTP request, the application can place rules on business methods to control who is allowed to call that operation.

In Spring for GraphQL, an operation may invoke multiple resolvers:

- Root resolvers such as `@QueryMapping` or `@MutationMapping`.
- Nested resolvers such as `@SchemaMapping`.
- Services and repositories invoked from resolvers.

A single GraphQL request can select multiple fields within the same operation. Therefore, checking permissions at the service layer helps protect business logic regardless of whether the method is called from a Query, Mutation, nested field, REST endpoint, or another processing flow.

For example, a user may have permission to read books but not edit books. The server must check permissions before executing an update operation, even if the client manually sends a Mutation that the user interface does not display.

Method security does not replace authentication at the HTTP/WebSocket transport. It adds an authorization layer where business logic is executed.

## 2. Enabling method security

For applications using imperative Spring Security, enable method security with `@EnableMethodSecurity`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

When `@EnableMethodSecurity` is enabled:

- `@PreAuthorize` and `@PostAuthorize` are supported by default.
- `@PreFilter` and `@PostFilter` also belong to the pre/post annotations group.
- `@Secured` is not enabled by default.
- JSR-250 annotations such as `@RolesAllowed` are not enabled by default.

If the application needs `@Secured` or `@RolesAllowed`, enable them explicitly:

~~~java
@Configuration
@EnableMethodSecurity(
        securedEnabled = true,
        jsr250Enabled = true
)
class MethodSecurityConfiguration {
}
~~~

Enable only the annotations your application actually uses. A method security configuration must be loaded in the Spring application context; simply adding annotations to methods without enabling the corresponding mechanism will not produce the expected permission checks.

## 3. Authentication and authorization

These two steps address two different questions:

- **Authentication:** who is calling?
- **Authorization:** is that caller allowed to perform this action?

For example, Spring Security may validate a token and create an `Authentication` representing user `alice`. This object may contain:

- Principal or username.
- Granted authorities.
- Authenticated status.
- Credentials or metadata according to the active security mechanism.

Method security uses the current `Authentication` to evaluate permission expressions. Never take a username or role from a GraphQL argument and treat it as an authenticated identity.

Example request a client might send:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
    }
}
~~~

`book-42` is the resource ID the client wants to access. That ID does not prove the client owns the book. The server must use the authenticated principal and backend permission data to decide.

## 4. Distinguishing roles and authorities

Spring Security represents permissions as authorities. An authority can describe a broad role or a fine-grained permission.

| Expression | Meaning |
| --- | --- |
| `hasAuthority('book:read')` | Checks that the exact authority `book:read` is present |
| `hasAuthority('book:write')` | Checks that the exact authority `book:write` is present |
| `hasRole('ADMIN')` | Checks the role with the default `ROLE_` prefix, equivalent to authority `ROLE_ADMIN` |
| `hasAnyRole('ADMIN', 'EDITOR')` | Caller has one of the specified roles |
| `isAuthenticated()` | Caller is authenticated |
| `permitAll()` | Allows anyone to invoke the method |
| `denyAll()` | Denies all invocations |

With `hasRole('ADMIN')`, do not include the `ROLE_` prefix in the argument. If you want to check an exact authority such as `book:read`, use `hasAuthority`.

In GraphQL applications, action-based authorities are often clearer than broad roles:

- `book:read`
- `book:write`
- `book:notes:read`
- `book:publish`

A user with the `EDITOR` role may be granted several read and write authorities, whereas an `AUDITOR` user only has read permissions. Rules mapping roles to authorities are managed in the authentication/authorization configuration.

## 5. Using @PreAuthorize to protect service methods

`@PreAuthorize` evaluates an expression before the target method is executed. If the expression is not satisfied, Spring Security rejects the call and the method body does not run.

Example:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class BookService {

    private final BookRepository repository;

    BookService(BookRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('book:read')")
    public Book findById(UUID id) {
        return repository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }

    @PreAuthorize("hasAuthority('book:write')")
    public Book update(UUID id, UpdateBookInput input) {
        Book book = repository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));

        book.setTitle(input.title());
        return repository.save(book);
    }
}
~~~

In the example:

- The caller must have `book:read` to look up a book.
- The caller must have `book:write` to update a book.
- If the authority is missing, the method body is not executed.
- Permissions are checked at the service boundary, regardless of which resolver calls the service.

Placing checks on services is especially useful when the same business logic is invoked from multiple GraphQL fields or different transports.

## 6. Connecting method security with GraphQL resolvers

Resolvers can focus on accepting arguments and delegating to protected services:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") UUID id) {
        return bookService.findById(id);
    }

    @MutationMapping
    public Book updateBook(
            @Argument("id") UUID id,
            @Argument("input") UpdateBookInput input) {
        return bookService.update(id, input);
    }
}
~~~

Corresponding SDL:

~~~graphql
input UpdateBookInput {
    title: String!
}

type Book {
    id: ID!
    title: String!
}

type Query {
    book(id: ID!): Book
}

type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book
}
~~~

When a client calls `Query.book`, the service checks `book:read`. When a client calls `Mutation.updateBook`, the service checks `book:write`.

You can place method security directly on controller methods in some designs, but protecting service methods enforces rules for every caller of the business logic. Never rely solely on the client UI hiding buttons or fields.

## 7. Protecting nested fields in GraphQL

GraphQL allows clients to select fields per object. Some fields may contain more sensitive data than others.

Example SDL:

~~~graphql
type Book {
    id: ID!
    title: String!
    internalNotes: String
}
~~~

The resolver for the sensitive field calls a service method with dedicated authorization:

~~~java
@SchemaMapping(typeName = "Book", field = "internalNotes")
public String internalNotes(Book book) {
    return bookService.readInternalNotes(book.getId());
}
~~~

Service:

~~~java
@PreAuthorize("hasAuthority('book:notes:read')")
public String readInternalNotes(UUID bookId) {
    return repository.findInternalNotesByBookId(bookId);
}
~~~

Users can read `id` and `title`, but cannot read `internalNotes` if they lack the `book:notes:read` authority.

Method security checks the service call when the resolver needs that field. GraphQL can return partial data along with an error for the denied field, depending on schema nullability and configured error handling.

One important note: field security must be applied to every access path to sensitive data. If `internalNotes` is also returned through another unprotected service method, a rule on one resolver is not enough to protect the data.

## 8. Checking object ownership and preventing IDOR

Checking only a general permission like `book:read` may not be enough. A user may have permission to read books, yet only be allowed to read books belonging to their own tenant or scope.

This is the object-level authorization problem. If an API only checks whether the user has a read authority and then queries by the client-supplied ID, a user can try IDs of resources belonging to someone else. This class of vulnerability is commonly called IDOR or broken object-level authorization.

You can check permissions with an authorization bean in the expression:

~~~java
import java.util.UUID;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;

@PreAuthorize("@bookAuthorization.canRead(authentication, #bookId)")
public Book findVisibleBook(@P("bookId") UUID bookId) {
    return repository.findById(bookId)
            .orElseThrow(() -> new BookNotFoundException(bookId));
}
~~~

Authorization bean:

~~~java
import java.util.UUID;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("bookAuthorization")
class BookAuthorization {

    private final BookAccessRepository accessRepository;

    BookAuthorization(BookAccessRepository accessRepository) {
        this.accessRepository = accessRepository;
    }

    public boolean canRead(Authentication authentication, UUID bookId) {
        String username = authentication.getName();

        return accessRepository.existsReadableBook(
                bookId,
                username
        );
    }
}
~~~

In the example, `bookId` comes from the client, whereas `username` comes from the trusted `Authentication`. The backend verifies the permission relationship between the principal and the resource.

For multi-tenant systems, the tenant must be determined from the security context or server-side membership data. Do not trust a `tenantId` sent by the client in GraphQL variables as proof that the user belongs to that tenant.

For large data queries, combine authorization with repository queries—for example, only loading records matching both `id` and the authenticated `tenant_id`. This reduces the risk of checking permissions only after loading out-of-scope data.

## 9. Using method parameters in security expressions

A `@PreAuthorize` expression sometimes needs to reference method parameters:

~~~java
@PreAuthorize("@bookAuthorization.canRead(authentication, #bookId)")
public Book findVisibleBook(@P("bookId") UUID bookId) {
    // ...
}
~~~

`@P("bookId")` from Spring Security names the parameter so the expression can explicitly reference it as `#bookId`.

You can use positional aliases like `#p0` or `#a0` when appropriate, though meaningful parameter names are generally easier to read and less error-prone.

Do not pass entire input objects into expressions when only a few values are needed. Keep authorization expressions concise and testable; move complex permission logic into a clearly named authorization bean.

## 10. Using @PostAuthorize to check results

`@PostAuthorize` evaluates an expression after the method completes and can access the return value via `returnObject`.

Example:

~~~java
import java.util.UUID;

import org.springframework.security.access.prepost.PostAuthorize;

@PostAuthorize(
        "returnObject == null || returnObject.ownerUsername == authentication.name"
)
public Book findPrivateBook(UUID id) {
    return repository.findById(id).orElse(null);
}
~~~

In the example, the result is only returned if the book does not exist or the book's owner matches the current principal. If the expression is not satisfied, Spring Security denies the call.

`@PostAuthorize` is useful when checking a property that is only available after the method returns a result. However, the method has already executed and data may have been loaded before the check.

Therefore:

- Use `@PreAuthorize` whenever permissions can be checked before the operation.
- Use `@PostAuthorize` for read operations where permission depends on the newly loaded object.
- Do not use `@PostAuthorize` as the protection mechanism for mutations with side effects; data writes may have already occurred before the post-check denies access.
- For sensitive queries, prefer filtering directly in the repository or service so out-of-scope data is never loaded if avoidable.

## 11. @PreFilter and @PostFilter

Spring Security also supports filtering collection elements using security expressions.

- `@PreFilter` filters input elements before the method runs.
- `@PostFilter` filters result elements after the method runs.

Example:

~~~java
@PostFilter("filterObject.ownerUsername == authentication.name")
public List<Book> findBooksForCurrentUser() {
    return repository.findAll();
}
~~~

This example removes books not belonging to the current user after the repository has already loaded the list.

With GraphQL, do not default to `@PostFilter` for every list-returning field. Some consequences:

- The repository may load a lot of unnecessary data.
- Pagination results and total counts may no longer accurately reflect the permitted dataset.
- Clients may receive pages with fewer items than expected.
- Post-load filtering can increase memory and time overhead.

Whenever possible, apply tenant/owner predicates directly in the database query and compute pagination over the authorized dataset.

## 12. @Secured and @RolesAllowed

In addition to pre/post annotations, simpler annotations can be used if the application enables them.

Example with `@Secured`:

~~~java
@Secured("ROLE_ADMIN")
public void publishBook(UUID bookId) {
    // Publish book.
}
~~~

Example with JSR-250 `@RolesAllowed`:

~~~java
@RolesAllowed("ADMIN")
public void archiveBook(UUID bookId) {
    // Archive book.
}
~~~

Configuration enabling both:

~~~java
@Configuration
@EnableMethodSecurity(
        securedEnabled = true,
        jsr250Enabled = true
)
class MethodSecurityConfiguration {
}
~~~

`@Secured` typically takes the exact authority/role name, such as `ROLE_ADMIN`. `@RolesAllowed` uses the role name and Spring applies the default role prefix during evaluation.

These annotations suit simple role rules. When you need to combine permissions, method parameters, object state, or policy beans, `@PreAuthorize` is more flexible.

## 13. Proxies and self-invocation

Spring method security relies on an AOP interceptor. Calls must pass through the Spring proxy so the security interceptor gets a chance to check permissions.

Several situations commonly cause checks not to run:

- Instantiating a service with `new` instead of injecting the bean from Spring.
- Calling a protected method from another method in the same instance via `this`.
- Placing annotations on a private method and expecting the proxy to intercept internal calls.
- Invoking the implementation directly rather than going through the Spring-managed proxy.

Self-invocation example:

~~~java
@Service
class BookService {

    public Book loadAndReadNotes(UUID id) {
        // This internal call does not go through the proxy.
        return readPrivateBook(id);
    }

    @PreAuthorize("hasAuthority('book:notes:read')")
    public Book readPrivateBook(UUID id) {
        return repository.findById(id).orElseThrow();
    }
}
~~~

If `loadAndReadNotes` calls `readPrivateBook` on the same object, method security may be bypassed because the call does not pass through the proxy.

A better structure is to move the protected method into another Spring service and inject that service:

~~~java
@Service
class PrivateBookReader {

    @PreAuthorize("hasAuthority('book:notes:read')")
    public Book readPrivateBook(UUID id) {
        // Load private book.
        return repository.findById(id).orElseThrow();
    }
}
~~~

Keep method security on public service boundaries, inject beans via constructors, and avoid self-invocation. When testing, obtain beans from the Spring context instead of instantiating classes manually.

## 14. Method security with reactive services

If a Spring GraphQL application uses WebFlux and services return `Mono` or `Flux`, configure reactive method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {
}
~~~

Reactive service example:

~~~java
import java.util.UUID;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
class ReactiveBookService {

    private final ReactiveBookRepository repository;

    ReactiveBookService(ReactiveBookRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('book:read')")
    public Mono<Book> findById(@P("bookId") UUID bookId) {
        return repository.findById(bookId);
    }

    @PreAuthorize("hasAuthority('book:read')")
    public Flux<Book> findAll() {
        return repository.findAll();
    }
}
~~~

Reactive method security uses the security context attached to the Reactor Context. Do not assume an imperative security context `ThreadLocal` is always present when publishers switch schedulers.

Principles:

- Use `@EnableReactiveMethodSecurity` for reactive method security.
- Keep publishers reactive and do not call `block()` in resolvers or services.
- Propagate context through the Reactor pipeline using Spring Security's supported mechanisms.
- Do not arbitrarily switch to another executor and assume the principal is automatically propagated.
- Test authorization with a real reactive pipeline.

`@EnableMethodSecurity` and `@EnableReactiveMethodSecurity` serve different execution models. Choose the configuration based on your service type and stack; do not mechanically enable both without understanding their respective interceptors.

## 15. Method security does not replace field and object authorization design

GraphQL lets clients choose fields, aliases, and nested relations. That does not mean the server is allowed to check permissions only at the root resolver.

Example operation:

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

Three different rules may be needed:

- Permission to read the book.
- Permission to read internal notes.
- Permission to view author details.

Define the security boundary for each business operation:

| Boundary | Example check |
| --- | --- |
| Root Query | Does the caller have `book:read`? |
| Sensitive nested field | Does the caller have `book:notes:read`? |
| Object-level | Does the book belong to the caller's tenant or scope? |
| Mutation | Does the caller have `book:write` and permission to edit the specific object? |
| Service | Every caller must adhere to the same business rules |

Do not rely on hiding schema fields or hiding UI buttons to protect data. Clients can submit arbitrary GraphQL documents; the server must check permissions at every necessary boundary.

## 16. Handling AccessDeniedException in GraphQL responses

When method security denies a call, Spring Security may throw `AccessDeniedException`. During GraphQL execution, the exception must be converted into a GraphQL error according to the API contract.

You can use `@GraphQlExceptionHandler` in a global `@ControllerAdvice` to return a safe message:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import java.util.Map;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.security.access.AccessDeniedException;

@ControllerAdvice
class GraphQlSecurityExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleAccessDenied(
            AccessDeniedException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.FORBIDDEN)
                .message("You do not have permission to perform this operation.")
                .extensions(Map.of("code", "FORBIDDEN"))
                .build();
    }
}
~~~

Do not return internal exception messages or stack traces to the client. If security policy requires avoiding disclosure of whether a resource exists, you can use the same message for both not-found and unauthorized cases.

A GraphQL response can contain partial data alongside an error on the denied field. If the field is declared non-null, null propagation can turn the parent field into null. Design nullability and the error contract consistently.

## 17. Testing method security in GraphQL

You should test through GraphQL operations to verify that resolvers, service proxies, and error mapping work together.

Spring Security Test provides `@WithMockUser` to establish an Authentication for tests. Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureHttpGraphQlTester
class BookMethodSecurityTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    @WithMockUser(authorities = "book:read")
    void readerCanQueryBook() {
        graphQlTester.document("""
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
                .isEqualTo("book-42");
    }

    @Test
    @WithMockUser
    void userWithoutBookAuthorityIsDenied() {
        graphQlTester.document("""
                query {
                    book(id: "book-42") {
                        id
                        title
                    }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors ->
                        assertThat(errors).anySatisfy(error ->
                                assertThat(error.getExtensions())
                                        .containsEntry("code", "FORBIDDEN")
                        )
                );
    }
}
~~~

This test assumes the application has configured the GraphQL HTTP tester, method security, and error advice. The `spring-security-test` dependency must be in test scope.

You should include test groups for:

- Users with the authority can read the corresponding Query.
- Users lacking the authority are denied before the service method executes.
- Users with `book:read` but lacking `book:write` cannot call the update Mutation.
- The `internalNotes` field is denied when lacking `book:notes:read`, while public fields still return data if the schema allows.
- Users cannot access objects belonging to another tenant by guessing IDs.
- `@PostAuthorize` rejects results not belonging to the caller.
- Reactive method security operates within the Reactor Context.
- Self-invocation does not create a call path that bypasses the security boundary.

Testing service methods directly is also useful, provided you obtain the bean from the Spring context so calls go through the proxy. GraphQL tests add proof that security is enforced on the actual API execution path.

## 18. Common issues

| Symptom | Cause | Solution |
| --- | --- | --- |
| `@PreAuthorize` has no effect | `@EnableMethodSecurity` not enabled or call does not go through proxy | Enable configuration and verify bean invocation |
| `@Secured` does not run | `securedEnabled` is still false | Enable `securedEnabled = true` |
| `@RolesAllowed` does not run | `jsr250Enabled` not enabled | Enable `jsr250Enabled = true` |
| `hasRole('ADMIN')` is always false | Authority lacks `ROLE_ADMIN` or wrong role mapping | Check role prefix and Authentication |
| User can read objects of another tenant | Only general authority checked, no ownership check | Add object-level authorization and tenant predicate |
| Mutation writes data before being denied | `@PostAuthorize` used on a method with side effects | Use `@PreAuthorize` before the operation |
| Self-invocation skips checks | Internal call bypasses proxy | Extract protected method into another bean |
| `@PostFilter` breaks pagination | Filtering happens after repository pagination | Filter in database query before pagination |
| Reactive authorization sees no principal | Security context not propagated in Reactor Context | Use reactive method security and proper context propagation |
| Client sees internal exception message | `AccessDeniedException` not safely mapped | Standardize GraphQL error message and code |
| UI hides field but API still returns data | Protection only implemented on frontend | Check permissions at resolver/service boundaries |

## 19. Workflow for implementing method security

When adding method security to a GraphQL API, follow this sequence:

1. **Identify business operations to protect.** List Queries, Mutations, and nested fields with sensitive data or actions.
2. **Establish identity.** Use the Authentication verified by Spring Security; never trust a username or tenant from the client.
3. **Define authorities.** Choose specific permissions such as `book:read`, `book:write`, and `book:notes:read`.
4. **Enable method security.** Use `@EnableMethodSecurity` for imperative or `@EnableReactiveMethodSecurity` for reactive.
5. **Place policies at service boundaries.** Use `@PreAuthorize` before operations requiring protection.
6. **Verify object ownership.** Combine the principal with owner/tenant in backend queries.
7. **Use post-checks intentionally.** Only use `@PostAuthorize` when permission depends on the result and the method causes no dangerous side effects.
8. **Verify proxies.** Avoid self-invocation and calling services outside the Spring container.
9. **Map errors safely.** Convert `AccessDeniedException` to a GraphQL error without leaking internal information.
10. **Test permissions.** Cover allowed users, denied users, sensitive fields, cross-tenant objects, and reactive execution.

## 20. Summary

Method security enables permission checks directly at business method invocations. In Spring for GraphQL, `@EnableMethodSecurity` activates annotations such as `@PreAuthorize` and `@PostAuthorize`; service methods can protect Queries, Mutations, and nested fields regardless of which resolver calls them.

Use `@PreAuthorize` to block before an operation runs, distinguish roles from authorities, and add object-level authorization to check owner or tenant. `@PostAuthorize` fits certain read operations but should not be used to protect mutations that have side effects. Because method security relies on Spring AOP proxies, avoid self-invocation. With WebFlux, use reactive method security and ensure the security context flows through the Reactor Context. Finally, map access-denied errors to safe GraphQL errors and test both allowed and denied cases with `GraphQlTester`.
