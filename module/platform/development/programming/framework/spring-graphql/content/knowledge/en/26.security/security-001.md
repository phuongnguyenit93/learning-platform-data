# Spring Security with GraphQL

Spring Security protects GraphQL applications at two primary levels: **authenticating requests to the endpoint** and **authorizing individual operations or resolved data**. HTTP URL security determines who can call the `/graphql` endpoint, but all Queries, Mutations, and nested fields typically share a single URL. Therefore, to restrict permissions by business logic, you need to combine method security on services or resolvers with permission checks on specific resources.

Spring for GraphQL supports Spring Security integration through context propagation. The security context can be used at the data fetching layer, even when GraphQL executes fields asynchronously. Spring for GraphQL also supports obtaining `Principal` or `@AuthenticationPrincipal` as parameters in annotated controllers.

## Authentication and authorization in GraphQL

Let's distinguish between two questions:

- **Authentication:** who is the caller? For example, a user logged in via session cookie, HTTP Basic, or bearer JWT.
- **Authorization:** what is that user allowed to do? For example, allowed to read public books, edit books belonging to an editorial group, or view internal notes.

A request can authenticate successfully and still lack permission to read a specific field. Conversely, a user may be allowed to read the book list but not allowed to run a Mutation to delete a book.

GraphQL typically has a single shared endpoint:

```text
POST /graphql
```

As a result, rules based solely on the URL cannot distinguish `Query.books`, `Mutation.deleteBook`, or `Book.internalNotes`. Authorization must be applied to the methods executing business logic or to field resolvers containing sensitive data.

## Protection layers in a GraphQL application

| Layer | Responsibility | Common mechanisms |
| --- | --- | --- |
| HTTP endpoint | Who is allowed to send requests to the GraphQL transport? | `SecurityFilterChain`, `authorizeHttpRequests`. |
| Authentication | Verify identity and create `Authentication`. | Session, HTTP Basic, OAuth2 Resource Server/JWT. |
| Operation/service | Who is allowed to run read or write business logic? | `@EnableMethodSecurity`, `@PreAuthorize`. |
| Resource/field | Does the user have permission on a specific record, tenant, or field? | Authorization service, `PermissionEvaluator`, method security. |
| Subscription | Who can subscribe and continue receiving which events? | Security at handshake/operation, permission checks, and filtering the event source. |
| GraphQL workload | Is the request consuming abnormal resources? | Rate limit, pagination, depth/complexity limits, and timeout. |

No single annotation replaces all of these layers. You should protect the endpoint at the HTTP boundary, protect business logic at the service layer, and check resource permissions where sufficient information is available to make the decision.

## Adding the Spring Security dependency

With Spring Boot and Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
}
```

With Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
```

Spring Security provides the servlet filter chain, authentication, and authorization. If the application uses Spring WebFlux, the corresponding security configuration will be reactive security (`SecurityWebFilterChain`); do not use servlet `SecurityFilterChain` in a WebFlux application.

## Protecting the GraphQL endpoint with SecurityFilterChain

Example requiring all requests to `/graphql` to be authenticated:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

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

With this configuration, unauthenticated requests are blocked at the servlet security filter before the GraphQL engine executes. Clients need to send a session cookie or credentials according to the authentication mechanism configured by the application.

If you change the endpoint path with `spring.graphql.http.path`, update the matcher accordingly. If the endpoint sits behind a context path or reverse proxy prefix, verify the path that the servlet filter actually receives.

URL rules only protect the shared endpoint. They do not automatically check permissions for individual fields. If some Queries are public and other Queries require login, you can let the endpoint pass through the filter and place method security on the services that need protection; however, you must ensure every business logic invocation path is protected.

## Enabling method security

To use `@PreAuthorize`, you need to enable method security in your configuration:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

`@EnableMethodSecurity` enables pre/post authorization annotations such as `@PreAuthorize` and `@PostAuthorize`. This is a separate configuration from URL authorization in `SecurityFilterChain`; enabling one mechanism does not automatically enable the other.

Method security works through a Spring AOP proxy. Therefore, calls need to go through the Spring bean proxy. A method calling another protected method within the same object via `this.someMethod()` can bypass the proxy and fail to trigger the security interceptor. Place protection boundaries on service beans injected and called from controllers or other services.

## Authorizing by authority and role

Spring Security can check an exact authority or a role:

```java
@Service
public class BookService {

    @PreAuthorize("hasAuthority('book:read')")
    public Book findById(String id) {
        // Load book
        return repository.findById(id).orElse(null);
    }

    @PreAuthorize("hasAuthority('book:write')")
    public Book update(String id, UpdateBookCommand command) {
        // Update book
        return repository.update(id, command);
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void delete(String id) {
        repository.deleteById(id);
    }
}
```

`hasAuthority("book:read")` compares against an authority with the exact name `book:read`. `hasRole("ADMIN")` checks for the authority `ROLE_ADMIN` by default; Spring Security automatically adds the `ROLE_` prefix when using `hasRole`.

Placing annotations on the service ensures the rules are enforced whether the service is called from GraphQL, a REST endpoint, a scheduled job, or another component via a Spring proxy. The controller only orchestrates requests and does not need to duplicate the same permission checks.

## Mapping GraphQL fields to protected services

Schema with a Query to read a book and a Mutation to update a book:

```graphql
type Book {
  id: ID!
  title: String!
  internalNotes: String
}

input UpdateBookInput {
  title: String!
}

type Query {
  book(id: ID!): Book
}

type Mutation {
  updateBook(id: ID!, input: UpdateBookInput!): Book!
}
```

The controller calls the service. Whether access is allowed or denied is decided by method security:

```java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @MutationMapping
    public Book updateBook(
            @Argument("id") String id,
            @Argument("input") UpdateBookInput input) {
        return bookService.update(id, input.toCommand());
    }
}
```

When a user lacks `book:read`, the `findById` call is denied. When lacking `book:write`, the Mutation cannot perform the update. The GraphQL runtime catches the exception from the resolution process and places it into `errors`; the response may still contain data for other fields that resolved successfully.

## Resource-level authorization

Checking general authorities is not enough if users are only allowed to read books belonging to their tenant or group. You can invoke an authorization bean from a SpEL expression in `@PreAuthorize`:

```java
@Component("bookAuthorization")
public class BookAuthorization {

    public boolean canRead(Authentication authentication, String bookId) {
        String userId = authentication.getName();
        return permissionRepository.canReadBook(userId, bookId);
    }
}
```

The service checks permission by ID before returning data:

```java
@Service
public class BookService {

    @PreAuthorize("@bookAuthorization.canRead(authentication, #p0)")
    public Book findReadableById(String id) {
        return repository.findById(id).orElse(null);
    }
}
```

`#p0` references the first parameter of the method, so it does not depend on Java parameter names being preserved at compile time. You can use `#id` when the project ensures parameter name metadata is available, such as compiling with `-parameters`.

The authorization service must check permissions based on the authenticated identity and server-side data. Do not use `userId`, `ownerId`, or `tenantId` sent by the client as proof that the caller owns the resource.

### Protecting nested fields

Suppose users are allowed to view basic book information, but only editors can read `internalNotes`. You can protect a dedicated service that provides this field:

```java
@Service
public class BookDetailsService {

    @PreAuthorize("hasAuthority('book:moderation:read')")
    public String getInternalNotes(String bookId) {
        return repository.findInternalNotes(bookId);
    }
}
```

The resolver simply calls the protected service:

```java
@Controller
public class BookFieldController {

    private final BookDetailsService detailsService;

    public BookFieldController(BookDetailsService detailsService) {
        this.detailsService = detailsService;
    }

    @SchemaMapping(typeName = "Book", field = "internalNotes")
    public String internalNotes(Book book) {
        return detailsService.getInternalNotes(book.getId());
    }
}
```

When the client lacks the appropriate authority, only the `internalNotes` field fails according to GraphQL nullability rules. Other fields such as `id` and `title` can still be returned. This is a more granular way to protect data than blocking the entire endpoint.

If a sensitive field depends on permissions per Book, use resource-based authorization instead of only checking general roles. You should also consider schema nullability: if a field is declared Non-Null, an error on that field can bubble up to the parent object and null out a larger part of `data`.

## Accessing Principal in annotated controllers

Spring for GraphQL supports `java.security.Principal` and `@AuthenticationPrincipal` as parameters in annotated controllers. You can use the user information for orchestration logic or pass the identifier to a service:

```java
import java.security.Principal;

@QueryMapping
public List<Book> myBooks(Principal principal) {
    return bookService.findByOwner(principal.getName());
}
```

Or obtain the Spring Security principal object directly:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;

@QueryMapping
public Profile myProfile(@AuthenticationPrincipal AppUser user) {
    return profileService.findByUserId(user.getId());
}
```

`Principal` keeps the code less coupled to Spring Security; `@AuthenticationPrincipal` is useful when the application has a custom principal type containing a user ID or identity details. You must handle the unauthenticated case if the endpoint allows anonymous requests; do not dereference the principal when it may be null.

Do not treat receiving a Principal as proof that every operation is allowed. Identity only answers who is calling; services still need to check authorities and resource permissions.

## Context propagation during asynchronous GraphQL execution

GraphQL may resolve multiple fields using `CompletableFuture`, Reactor, or DataLoader. Execution may continue on a thread different from the one that received the HTTP request. Spring for GraphQL supports context propagation so that the Security context and other contexts are available at the data fetching layer.

This enables method security on services to work during GraphQL field resolution. However, if the application creates its own executor or launches detached work outside the GraphQL execution mechanism, you need to account for propagating the corresponding context. Do not assume every `ThreadLocal` automatically appears on every thread.

Best practices:

- Prefer calling protected service beans from resolvers and let Spring manage context propagation.
- For custom executors, configure an appropriate `SecurityContext` propagation mechanism if tasks require authentication information.
- Do not use `CompletableFuture.supplyAsync` with the common pool and expect `SecurityContextHolder` to always be populated.
- Pass the authenticated tenant/user ID explicitly when work is queued or run in the background.
- Do not store `Authentication` in a mutable singleton field or a cache shared across requests.

With Reactor, keep the reactive pipeline intact and avoid switching unnecessarily to threads without context. When integrating blocking libraries, you must both manage the dispatcher/executor and ensure the necessary context is safely propagated.

## Handling AccessDeniedException in GraphQL responses

When the HTTP security filter rejects a request before the GraphQL engine runs, the client typically receives HTTP 401 or 403. When method security rejects a service while GraphQL is resolving a field, it is a GraphQL execution error. The response typically contains `errors` and may include partial `data`; the HTTP status is usually still 200 because the operation was accepted and execution began.

You can use `@GraphQlExceptionHandler` in a controller or `@ControllerAdvice`, or a `DataFetcherExceptionResolver` for the corresponding DataFetcher, to map `AccessDeniedException` to a public message and appropriate error classification.

Example standardized response:

```json
{
  "data": {
    "book": {
      "id": "book-10",
      "title": "Spring in Practice",
      "internalNotes": null
    }
  },
  "errors": [
    {
      "message": "You do not have permission to view internal notes",
      "path": ["book", "internalNotes"],
      "extensions": {
        "code": "FORBIDDEN"
      }
    }
  ]
}
```

This is an illustrative response for a nullable field. Do not expose stack traces, SQL statements, internal class names, or sensitive policy details to the client. Internal logs can store a correlation ID and error type according to your security policy.

Do not turn every error into `null` without an error entry. Clients need to distinguish between a field genuinely having no data and a field whose access was denied.

## Protecting Mutations and avoiding post-write permission checks

Mutations change state, so they require authorization before performing side effects. Place `@PreAuthorize` on service methods that write data:

```java
@Service
public class BookCommandService {

    @PreAuthorize("@bookAuthorization.canEdit(authentication, #p0)")
    @Transactional
    public Book update(String bookId, UpdateBookCommand command) {
        Book book = repository.findById(bookId).orElseThrow();
        book.rename(command.title());
        return repository.save(book);
    }
}
```

Do not use `@PostAuthorize` as the primary protection layer for write operations. That annotation checks the result after the method has already run; if the method has already committed changes before discovering the caller lacks permission, side effects may have already occurred. For write operations, check permissions before mutating data and enforce invariants in the service/domain.

If permission depends on the state of a record, you can load the record in the service and check authorization before updating within the same transaction. Consider race conditions and use optimistic/pessimistic locking or conditional database updates when appropriate.

## Securing DataLoader and `@BatchMapping`

DataLoader batches multiple relational field loads into a single batch. A batch loader is still a data access path and must follow the same authorization policies as a regular resolver.

For example, do not let a batch loader load all authors based solely on IDs provided by source objects while ignoring the tenant. The batch service should receive the authenticated tenant or user scope and filter data on the server:

```java
public Map<Long, Author> findVisibleAuthors(
        String tenantId, Set<Long> authorIds) {
    return authorRepository.findVisibleByTenantAndIdIn(tenantId, authorIds);
}
```

Within a GraphQL request, a DataLoader is typically created per request and cached by key. Do not share a DataLoader or cache sensitive results as a singleton across users. If a batch key is insufficient to distinguish data scopes within the same registry, design the key or loader context to include the required scope.

With `@BatchMapping`, check permissions in the service called by the batch method or filter the data source before returning the map/list. Do not assume that because a parent resolver checked permissions, all child fields and all batch loaders are automatically secure.

## Securing Subscriptions

Subscriptions have a longer lifecycle than a typical HTTP request. You need to check permissions when the client starts subscribing and define a policy for when permissions change while the stream is still active.

Key points to handle:

- Authenticate at the WebSocket handshake or the corresponding transport mechanism.
- Check permissions to subscribe to the Subscription operation and the requested resource.
- Filter the event source by the authenticated user, tenant, and resource.
- Do not broadcast sensitive events to all subscribers and rely on the selection set to hide data.
- Define behavior when a token expires, the user logs out, or permissions are revoked.
- Cancel the subscription and release listeners when no longer permitted or when the client sends complete.

Method security on `@SubscriptionMapping` can protect the subscription initiation step. However, the event producer may run on a different thread and emit events long afterward; do not assume the request's `SecurityContextHolder` is always available on the producer thread. Bind the subscription to the authenticated scope, filter at the event source, and implement cancellation/revalidation if business requirements demand it.

## CSRF and CORS with GraphQL HTTP

GraphQL typically uses a single POST endpoint for both Queries and Mutations. If the application authenticates with session cookies, browsers automatically send cookies according to their rules; therefore, Spring Security's CSRF protection remains important for mutations.

Do not disable CSRF for the entire application just to make GraphQL requests work. If using cookie sessions, configure how the frontend retrieves and sends the CSRF token. If the API uses bearer tokens in the Authorization header and does not rely on automatically sent cookies, evaluate CSRF based on the actual authentication model.

CORS controls whether a frontend from another origin is allowed to call the endpoint and send the required headers. CORS does not authenticate users and does not replace authorization. When enabling credentials, declare specific origins; do not combine credentials with a wildcard origin.

## Query controls and resource abuse

An authorized user can still send an overly deep operation or request a massive amount of data. GraphQL security must consider both access permissions and resource limits:

- Enforce pagination and maximum `first`/`last` limits.
- Limit query depth or complexity according to an appropriate configuration.
- Rate limit by user, API key, or client identity.
- Set timeouts for GraphQL operations and downstream services.
- Limit the number of aliases, batch requests, or concurrent subscriptions if the transport allows them.
- Disable or restrict introspection in environments requiring that policy, but do not treat hiding the schema as authorization.
- Monitor resource-intensive operations and error/timeout rates.

Introspection only provides information about the schema; disabling introspection does not prevent a user who already knows field names from accessing data. Authorization must be enforced in resolvers/services for each field and resource.

## Testing security for GraphQL

Testing needs to cover both endpoint security and method security. For method security, you can use `@WithMockUser` to create an Authentication in tests:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class BookServiceSecurityTests {

    private final BookService bookService;

    BookServiceSecurityTests(BookService bookService) {
        this.bookService = bookService;
    }

    @Test
    @WithMockUser(authorities = "book:read")
    void readerCanReadBook() {
        assertThat(bookService.findById("book-10")).isNotNull();
    }

    @Test
    @WithMockUser(authorities = "book:write")
    void writerCannotUseReadOnlyAuthority() {
        assertThatThrownBy(() -> bookService.findById("book-10"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
```

The example assumes the service bean is injected from a Spring application context with `@EnableMethodSecurity` enabled; do not manually instantiate `new BookService(...)` as that bypasses the AOP proxy and does not evaluate annotations.

Tests require the `spring-boot-starter-test` and `spring-security-test` dependencies in the test scope. The `book-10` data needs to be prepared in fixtures or a test database for the success assertion to be meaningful.

To test GraphQL end-to-end, use `GraphQlTester` or an HTTP tester with the real security filter chain. You should verify:

- Anonymous requests are blocked at the endpoint if the endpoint requires authentication.
- Users with the appropriate authority can execute the corresponding Query/Mutation.
- Users lacking the authority receive an appropriate GraphQL error on the protected field.
- Users cannot access resources belonging to another user or tenant even if they know the ID.
- Sensitive fields are denied while public fields can still be returned if nullability allows.
- Batch loaders do not bypass tenant/resource authorization.
- Subscriptions only receive events within the allowed scope and cancellation works.
- CSRF tokens and CORS are checked properly for the authentication type.
- No stack traces, tokens, or sensitive data are leaked in errors/extensions/logs.

With HTTP tests using MockMvc, you can use Spring Security Test to attach a user and CSRF token to the request. With WebSocket Subscriptions, you must test both connection authentication and operation permissions; a test calling the service directly does not prove the handshake is protected.

## Common issues

| Symptom | Cause | Solution |
| --- | --- | --- |
| The `/graphql` endpoint allows anonymous access | `SecurityFilterChain` is not protecting the right path or another filter chain is applied first. | Check matchers, filter chain ordering, and the actual path. |
| Logged in, yet the service still reports AccessDenied | Missing authority or wrong role/authority prefix used. | Check `GrantedAuthority`, `hasRole`, and `hasAuthority`. |
| `@PreAuthorize` does not run | `@EnableMethodSecurity` is not enabled or the call bypasses the proxy via self-invocation. | Enable method security and call through a Spring bean proxy. |
| Nested GraphQL field leaks data | Only the root Query is protected; child fields/services are not protected. | Protect the service providing the sensitive field and check resource permissions. |
| Async DataFetcher loses Authentication | Custom executor does not propagate SecurityContext. | Use context propagation or an executor that propagates SecurityContext appropriately. |
| DataLoader returns another tenant's data | Batch loader does not apply tenant scope or uses a shared cache. | Filter in the batch service and keep the loader/cache per request. |
| Method security returns a GraphQL error but HTTP status is still 200 | The error occurred after the GraphQL operation started executing. | Clients should read `errors` and handle partial `data`; do not assume this is a transport error by default. |
| Mutation changes data before being denied | `@PostAuthorize` was used to protect a write operation. | Check permissions before side effects using `@PreAuthorize` and service/domain invariants. |
| Subscription keeps emitting after permissions are revoked | Permissions were only checked at subscribe time. | Revalidate, cancel the stream, or limit subscription duration by policy. |

## Key takeaways

Protecting GraphQL with Spring Security requires combining URL security and method security. `SecurityFilterChain` authenticates requests to the shared endpoint; `@EnableMethodSecurity` enables `@PreAuthorize` to protect service methods executing individual business operations. Use authorities or roles for general permissions, and an authorization service to check permissions per resource/tenant.

Spring for GraphQL supports obtaining `Principal` or `@AuthenticationPrincipal` in annotated controllers and context propagation so the security context is available at the data fetching layer. For custom async executors, DataLoader, batch mapping, and Subscriptions, ensure the authenticated context or scope is properly propagated and filtered. Handle `AccessDeniedException` into safe GraphQL errors, preserving the distinction between HTTP filter errors and errors during field resolution. Finally, test anonymous access, individual authorities, resource ownership, tenant isolation, CSRF/CORS, and the subscription lifecycle.

## References

- [Spring for GraphQL — Security](https://docs.spring.io/spring-graphql/reference/security.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
