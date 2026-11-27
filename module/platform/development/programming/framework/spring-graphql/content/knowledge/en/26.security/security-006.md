# Field-level authorization

## Objectives

After this lesson, you will be able to:

- Distinguish authentication, HTTP endpoint authorization, and per-field GraphQL authorization.
- Explain why a shared GraphQL URL requires permission checks at the method or service level.
- Enable method security with @EnableMethodSecurity.
- Use @PreAuthorize to protect root resolvers and nested fields through services.
- Write authorization rules based on authorities, owners, tenants, and the target object.
- Protect batch resolvers when each parent object has different access permissions.
- Understand how AccessDeniedException becomes a GraphQL error and the impact of nullability.
- Test access permissions using Spring Security Test and GraphQlTester.

## Why is field-level authorization needed?

A GraphQL endpoint typically shares a single URL, such as POST /graphql. Many different operations go through that same endpoint:

- Queries for public books.
- Queries for internal book information.
- Mutations to update books.
- Queries for the current user's information.

If you only configure HTTP security for the /graphql URL, the server can determine whether the sender is logged in, but it cannot tell from that URL which fields the operation is reading or which mutation is being executed.

GraphQL allows clients to select arbitrary fields in the selection set. A single query can fetch a public title alongside sensitive internalNotes:

~~~graphql
query {
  bookById(id: "book-101") {
    title
    internalNotes
  }
}
~~~

A user permitted to read books may not have permission to read internal notes. Therefore, authorization must be applied to the specific piece of data or operation.

Spring for GraphQL recommends using Spring Security annotations such as @PreAuthorize or @Secured on service methods that provide data for each part of the response. The security context is propagated to the data fetching layer so those methods can use the current identity. This also protects the service if it is called from another entry point outside GraphQL.

## Distinguishing authentication and authorization

These two concepts address two different questions:

- Authentication determines who the caller is.
- Authorization determines what that caller is allowed to do with specific data or operations.

Examples:

| User | Authentication | Grantable permissions |
| --- | --- | --- |
| Unauthenticated user | Anonymous | Read public book information |
| Member | Logged in | Read books and their own profile |
| Editor | Logged in | Create and update books |
| Internal staff | Logged in | Read internal notes |
| Administrator | Logged in | Manage users and configuration |

Do not treat being logged in as proof that the user is allowed to read every field. A principal can hold various authorities; policies must check the right permission for each use case.

## Combining HTTP security and method security

HTTP security controls access to the transport endpoint. For instance, an application may require every request to /graphql to be authenticated:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/graphql").authenticated()
                    .anyRequest().permitAll())
            .build();
}
~~~

This is endpoint-level control. If the API has both public and private operations, the HTTP policy can allow requests to reach the endpoint, then use method security to protect private data. That decision depends on how the application handles anonymous operations.

Enable method security with @EnableMethodSecurity:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Merely adding spring-boot-starter-security does not automatically enable method authorization. @EnableMethodSecurity is required for Spring to create interceptors for @PreAuthorize, @PostAuthorize, and default method security annotations.

When method security is enabled, annotations are applied on Spring-managed beans and executed via AOP proxies. Therefore, methods must be invoked through the Spring bean proxy. Internal calls such as this.securedMethod() within the same bean can bypass the proxy and fail to trigger @PreAuthorize.

## Protecting root fields and nested fields

Example schema with one public field and one internal field:

~~~graphql
type Query {
  bookById(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  internalNotes: String
}
~~~

The internalNotes field is declared nullable. This allows GraphQL to keep the public fields of Book if reading the notes is denied and the error is handled at that field.

### Protecting read operations in the service

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class BookService {

    @PreAuthorize("hasAuthority('book:read')")
    public Book findById(String id) {
        return bookRepository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }

    @PreAuthorize("hasAuthority('book:internal:read')")
    public String findInternalNotes(String bookId) {
        return bookRepository.findInternalNotes(bookId);
    }

    @PreAuthorize("hasAuthority('book:write')")
    public Book update(String id, UpdateBookInput input) {
        return bookRepository.update(id, input);
    }
}
~~~

Each method has a clear permission:

- book:read allows reading books.
- book:internal:read allows reading internal notes.
- book:write allows updating books.

Do not lump all permissions into a single generic authority such as authenticated. Authorities should reflect the actions or data the API is protecting.

### Nested resolver calling a protected service

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "internalNotes")
    public String internalNotes(Book book) {
        return bookService.findInternalNotes(book.id());
    }
}
~~~

When the client selects Book.internalNotes, GraphQL invokes that field's resolver. The resolver calls BookService.findInternalNotes; Spring Security checks the authority before the service method executes.

If a user has book:read but lacks book:internal:read, they can still read title while internalNotes is denied. Permissions are checked right where sensitive data is retrieved.

Do not let a sensitive property be read automatically via the default property data fetcher without control. If Book has an internalNotes getter and no protected resolver, GraphQL may read that property directly. For sensitive fields, provide a resolver/service with explicit authorization or exclude sensitive data from the source object.

## Object-level and ownership authorization

A general authority is insufficient when permission depends on the specific object. For example, a user may edit books they own, but not books owned by someone else.

You can place the policy in a dedicated bean:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("bookAuthorization")
public class BookAuthorization {

    private final BookPermissionService permissionService;

    public BookAuthorization(BookPermissionService permissionService) {
        this.permissionService = permissionService;
    }

    public boolean canReadInternalNotes(
            String bookId,
            Authentication authentication) {

        return permissionService.canReadInternalNotes(
                authentication.getName(), bookId);
    }

    public boolean canUpdate(
            String bookId,
            Authentication authentication) {

        return permissionService.canUpdate(
                authentication.getName(), bookId);
    }
}
~~~

The service can invoke the policy with SpEL:

~~~java
@PreAuthorize(
        "hasAuthority('book:internal:read') and " +
        "@bookAuthorization.canReadInternalNotes(#p0, authentication)")
public String findInternalNotes(String bookId) {
    return bookRepository.findInternalNotes(bookId);
}

@PreAuthorize(
        "@bookAuthorization.canUpdate(#p0, authentication)")
public Book update(String bookId, UpdateBookInput input) {
    return bookRepository.update(bookId, input);
}
~~~

In the example, #p0 is the first method parameter. You can use parameter names in SpEL if the build retains parameter name metadata or use Spring Security's @P annotation to name parameters explicitly. Avoid relying on parameter names that are not preserved after compilation.

Policies should check ownership or tenant on the server. Never trust an ownerId, tenantId, or role sent by the client in GraphQL arguments. Clients only send the target resource ID; the server looks up and compares it against the authenticated principal.

For mutations, prefer checking permissions before writing data using @PreAuthorize. Do not use @PostAuthorize to check permissions after the method has already modified the database, because side effects may have already occurred before the result is rejected.

## Reading principal in annotated controllers

Spring for GraphQL supports binding Principal or @AuthenticationPrincipal to controller parameters when a Spring Security context is present:

~~~java
import java.security.Principal;
import java.util.List;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class CurrentUserController {

    private final BookService bookService;

    public CurrentUserController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> myBooks(Principal principal) {
        return bookService.findOwnedBy(principal.getName());
    }
}
~~~

Or obtain a specific principal type:

~~~java
@QueryMapping
public UserProfile me(
        @AuthenticationPrincipal AppPrincipal principal) {
    return userService.profile(principal.userId());
}
~~~

Principal and @AuthenticationPrincipal let controllers read the current identity. They do not replace authorization in services. Services still need to protect sensitive operations because the same method may be called from multiple code paths.

Do not take a username or userId from a GraphQL argument as a substitute for the principal. If a query accepts a userId argument, the server must verify the caller is permitted to access that user.

## Protecting @BatchMapping

Batch mapping consolidates loading a nested field for multiple parent objects. That reduces N+1 queries but also complicates authorization: a single batch call can contain multiple Books belonging to different owners or tenants.

A general permission can be checked on the batch method:

~~~java
@Service
public class AuthorService {

    @PreAuthorize("hasAuthority('author:read')")
    public Map<Book, Author> findAuthorsForBooks(List<Book> books) {
        // Bulk load authors for the requested books.
        return loadAuthors(books);
    }
}
~~~

The author:read permission only proves the caller is allowed to use the author-reading feature. It does not automatically prove the caller is allowed to read the author linked to every Book in the list.

If policy varies per parent object, filter or check each key in the service/repository:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(
        List<Book> books,
        Principal principal) {

    return authorService.findAuthorsVisibleTo(
            books, principal.getName());
}
~~~

findAuthorsVisibleTo must apply policy to each Book before loading or returning its Author. For relationships that are not allowed to be displayed, the API can choose to mask them with null or report per-field errors, depending on the contract and security requirements. Never return results from another tenant simply because keys were grouped into the same batch.

When using Map<Book, Author>, keys must match the source objects accurately and equality/hashCode must be stable. If using a result List, the exact source order must be preserved. Authorization must not break alignment between Books and Authors.

For multi-tenant data, the safest and most efficient approach is usually placing tenant/owner conditions directly into the bulk repository query so the database only returns records within the permitted scope. Do not load all data and filter only in the controller.

## Field-level authorization vs. hiding fields on the client

Hiding a field in the UI does not protect data. Clients can submit a different GraphQL document, use aliases, use fragments, or call the endpoint directly.

The @skip and @include directives only control whether a field is executed within an operation; they are not an authorization mechanism.

Likewise, not displaying a field in the UI or omitting a field from sample queries does not prevent an authorized or unauthorized user from sending another query requesting that field.

Authorization must run on the server for every access path:

- Root queries.
- Nested fields.
- Mutations.
- Batch resolvers and DataLoaders.
- Resolvers invoked via services or other entry points.

Return DTOs containing only the necessary data and keep sensitive attributes behind protected service methods. Never rely on field naming conventions or the assumption that clients do not know the schema.

## AccessDeniedException and GraphQL errors

When @PreAuthorize denies access, Spring Security throws AccessDeniedException. In GraphQL, this error occurs during field resolution, so the response may contain partial data alongside an error whose path points to the denied field.

Example:

~~~json
{
  "data": {
    "bookById": {
      "id": "book-101",
      "title": "Spring GraphQL",
      "internalNotes": null
    }
  },
  "errors": [
    {
      "message": "Access is denied",
      "path": ["bookById", "internalNotes"]
    }
  ]
}
~~~

Spring GraphQL provides ErrorType.FORBIDDEN and ErrorType.UNAUTHORIZED to classify authorization errors. SecurityDataFetcherExceptionResolver is a built-in resolver for handling Spring Security exceptions in applications using non-reactive transports, such as Spring MVC. For WebFlux or custom error policies, register an appropriate resolver and test the actual classification in your version.

If an exception is not handled by any resolver, Spring for GraphQL defaults to classifying it as INTERNAL_ERROR with a generic message. Therefore, do not assume every AccessDeniedException automatically becomes FORBIDDEN across every stack or configuration.

Nullability in SDL determines the scope of error propagation:

| Field declaration | When the resolver is denied |
| --- | --- |
| internalNotes: String | The field can become null; sibling fields can still be returned |
| internalNotes: String! | Null propagates up to the nearest nullable Book parent object |
| bookById: Book! and non-null child field fails | The error can propagate all the way to root data |

Do not change a field to nullable solely to mask authorization errors. Choose nullability according to the data contract and explicitly decide whether the API should report an error or conceal the resource's existence.

If you want to avoid disclosing whether a resource exists, the policy can return NOT_FOUND for both non-existent and unauthorized cases. Apply this consistently to prevent ID enumeration channels.

## Testing authorization

Test at two levels:

1. Service tests verifying that method security actually blocks the operation.
2. GraphQL integration tests verifying that permissions are enforced through resolvers and responses have appropriate paths/errors.

Example service test:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class BookServiceSecurityTests {

    @Autowired
    private BookService bookService;

    @Test
    @WithMockUser(authorities = "book:internal:read")
    void internalReaderCanReadNotes() {
        String notes = bookService.findInternalNotes("book-101");
        assertThat(notes).isNotNull();
    }

    @Test
    @WithMockUser(authorities = "book:read")
    void regularReaderCannotReadInternalNotes() {
        assertThatThrownBy(
                () -> bookService.findInternalNotes("book-101"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

To run tests, add spring-security-test to test dependencies. For object-level policies, write tests for the right owner, a different owner, a different tenant, and an anonymous principal.

GraphQL integration tests should send queries containing both public and protected fields. Use security test support matching the transport:

- Spring MVC: MockMvc with Spring Security test support or WebGraphQlTester via the corresponding security configuration.
- Spring WebFlux: WebTestClient and SecurityMockServerConfigurers.

Verify that public fields still return data, sensitive fields are denied, the error path points accurately to the nested field, and the error classification is FORBIDDEN or UNAUTHORIZED based on the principal. If a field is non-null, also verify null propagation up to the parent.

You should test:

- Anonymous users cannot call operations requiring authentication.
- Users with book:read cannot read internalNotes.
- Users with book:internal:read can read internalNotes.
- Users can only edit books within their allowed scope.
- Aliases and fragments do not bypass authorization.
- Batch mappings do not return cross-tenant data.
- Mutations are rejected before any side effects occur.
- Other resolvers still return partial data when an independent field is denied.

## Common issues

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| @PreAuthorize has no effect | @EnableMethodSecurity not enabled | Enable method security in configuration |
| Protected /graphql yet sensitive fields still leak | HTTP URL security only controls the endpoint | Protect the service method supplying the field |
| Sensitive field is still returned | Default property fetcher reads getter directly | Create a resolver calling a protected service or remove sensitive data from source object |
| Permission skipped when service calls a method in the same bean | Self-invocation goes through this instead of proxy | Move the protected method to another bean or call via proxy |
| User reads objects of another tenant | Only role checked, no ownership/tenant check | Use object-level policy and tenant condition in repository |
| Batch mapping leaks cross-tenant data | Only general permission checked for the entire batch | Apply per-source/per-key policy or bulk query with tenant scope |
| AccessDeniedException becomes INTERNAL_ERROR | No suitable resolver or resolver not registered | Configure security exception resolver and check MVC/WebFlux stack |
| Entire parent object becomes null | Denied field is declared non-null | Review nullability and response contract |
| Mutation writes data before being denied | Post-condition check used for write operation | Check permissions before performing side effects |
| Client passes userId to read another user's data | Trusting client input instead of principal | Obtain identity from SecurityContext and verify object ownership |

## Comprehensive practice

Build field-level authorization for a library API:

1. Declare Book.internalNotes as a sensitive field in SDL.
2. Create authorities book:read, book:internal:read, and book:write.
3. Enable method security with @EnableMethodSecurity.
4. Protect BookService.findById, findInternalNotes, and update with @PreAuthorize.
5. Create BookAuthorization to check ownership or tenant when needed.
6. Write @SchemaMapping for internalNotes calling the protected service.
7. Create @BatchMapping for Book.author and check permissions per Book if policy depends on parent object.
8. Configure a GraphQL error resolver so AccessDeniedException is classified properly.
9. Test anonymous, reader, internal reader, editor, and owner using @WithMockUser.
10. Write GraphQL integration tests to verify partial data, error paths, and null propagation.

After completing, explain why URL security is insufficient for GraphQL, why service-level authorization protects multiple entry points, and how to avoid data leaks when batch resolvers load many objects at once.

## Key takeaways

GraphQL uses a shared endpoint, so HTTP URL security only provides coarse-grained control. To authorize per field, enable @EnableMethodSecurity and place @PreAuthorize on service methods providing data or executing operations. Use authorities for general permissions, and policy beans for ownership and tenant scope. Protect nested fields, batch mappings, and all service access paths; never rely on the UI or GraphQL selection sets to hide data. AccessDeniedException must be mapped to an appropriate GraphQL error; nullability determines partial responses vs. null propagation. Test with Spring Security Test and GraphQlTester to confirm both access permissions and the actual data returned.

## References

- [Spring for GraphQL – Security](https://docs.spring.io/spring-graphql/reference/security.html)
- [Spring for GraphQL – Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring GraphQL – SecurityDataFetcherExceptionResolver API](https://docs.spring.io/spring-graphql/docs/2.0.x/api/org/springframework/graphql/execution/SecurityDataFetcherExceptionResolver.html)
