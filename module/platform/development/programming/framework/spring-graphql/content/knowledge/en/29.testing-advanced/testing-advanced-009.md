# Testing authorization

## Objectives

After this lesson, you will be able to:

- Explain why authorization must be tested at both the HTTP endpoint and individual GraphQL fields.
- Distinguish authentication from authorization.
- Enable method security with `@EnableMethodSecurity`.
- Protect service methods with `@PreAuthorize` and `@PostAuthorize`.
- Create test users with specific roles and authorities.
- Use `@WithMockUser`, `@WithAnonymousUser`, and `spring-security-test`.
- Test field-level authorization through `GraphQlTester`.
- Send credentials through `HttpGraphQlTester` when testing HTTP integration.
- Distinguish HTTP 401/403 from GraphQL execution errors.
- Verify partial data, error paths, and that sensitive data is not returned.
- Recognize common pitfalls when testing security in Spring for GraphQL.

## 1. Authentication and authorization in GraphQL

Authentication answers the question: who sent the request? Authorization answers the question: what actions or data is that person allowed to perform or read?

In a REST API, each endpoint typically has its own URL. In GraphQL, multiple operations share a single endpoint, typically `/graphql`. Consequently, securing the URL alone blocks unauthenticated callers, but is insufficient to differentiate access permissions across Queries, Mutations, or individual fields.

For example, two users both send requests to `POST /graphql`:

- One user has permission to read public book details.
- Another user additionally has permission to read internal book notes.

Both may be permitted to call the endpoint and execute the `bookById` Query, yet only the user with the matching authority should be allowed to read the `privateNotes` field.

Spring for GraphQL recommends combining two layers:

1. Request-level security protects the endpoint and authenticates requests.
2. Method-level security protects the service methods performing specific work for each piece of data.

Thanks to context propagation, the Spring Security context can travel from the HTTP transport through the GraphQL engine to DataFetchers. As a result, annotations such as `@PreAuthorize` on service methods are enforced when GraphQL resolves fields.

## 2. Endpoint protection does not replace field authorization

You can configure Spring Security to require authentication before accessing the GraphQL endpoint:

~~~java
@Configuration
class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/graphql").authenticated()
                        .anyRequest().permitAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

The example above uses HTTP Basic to illustrate authentication. Production applications may use sessions, OAuth2 Resource Server, JWT, or other authentication mechanisms.

If a request lacks valid credentials, Spring Security can block it before the GraphQL engine executes the operation. Depending on the authentication and authorization setup, the HTTP response can be:

- `401 Unauthorized`: the request has not been validly authenticated.
- `403 Forbidden`: the user is authenticated but not allowed to access the endpoint.

When the endpoint only permits logged-in users, every GraphQL operation sharing that URL passes through that gate. That gate cannot substitute for per-operation permissions on `bookById`, `privateNotes`, or a specific mutation.

For GraphQL APIs using browser session cookies, retain and test CSRF protection. The HTTP Basic example above does not disable CSRF. Only consider disabling CSRF for stateless APIs once the authentication architecture and how clients transmit credentials have been properly evaluated.

## 3. Enabling method security

Spring Boot Starter Security does not enable method-level authorization automatically. Add `@EnableMethodSecurity` to a configuration class:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Once enabled, Spring Security can enforce annotations such as:

- `@PreAuthorize`: checks permissions before invoking the method.
- `@PostAuthorize`: checks the result before returning to the caller.
- `@PreFilter` and `@PostFilter`: filters arguments or results using expressions.
- `@Secured`: an older mechanism requiring `securedEnabled = true`.

In most new code, prefer `@PreAuthorize` because it can inspect roles, authorities, method arguments, and authorization beans.

## 4. Protecting service methods with @PreAuthorize

Suppose the GraphQL API lets users read basic book details, while only certain users can view internal notes.

Schema:

~~~graphql
type Query {
  bookById(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  privateNotes: String
}
~~~

Service responsible for reading internal notes:

~~~java
@Service
public class BookAccessService {

    @PreAuthorize("hasAuthority('book:private:read')")
    public String findPrivateNotes(String bookId) {
        return "Internal review: verify publisher contract";
    }
}
~~~

`@PreAuthorize` is evaluated before the method runs. The user must hold the exact authority `book:private:read`.

Controller mapping GraphQL fields:

~~~java
@Controller
public class BookController {

    private final BookService bookService;
    private final BookAccessService bookAccessService;

    public BookController(
            BookService bookService,
            BookAccessService bookAccessService) {
        this.bookService = bookService;
        this.bookAccessService = bookAccessService;
    }

    @QueryMapping
    public Book bookById(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "privateNotes")
    public String privateNotes(Book book) {
        return bookAccessService.findPrivateNotes(book.id());
    }
}
~~~

When a client queries:

~~~graphql
query {
  bookById(id: "b-01") {
    id
    title
    privateNotes
  }
}
~~~

GraphQL executes the root field `bookById`, then resolves `privateNotes`. When the DataFetcher invokes `BookAccessService.findPrivateNotes(...)`, Spring Security checks the current user's authorities.

If the user lacks permission, the method is denied and GraphQL records an error on the corresponding field. Because `privateNotes` is declared nullable, basic `Book` data can still be returned.

Placing authorization on the service protects data even if the service is invoked from another GraphQL field, a REST endpoint, or an internal flow. Never rely solely on hiding fields in the client UI as a security control.

## 5. Distinguishing roles and authorities

Spring Security distinguishes between roles and authorities:

- `hasRole('ADMIN')` checks an authority with the default `ROLE_` prefix, i.e., `ROLE_ADMIN`.
- `hasAuthority('book:private:read')` checks the exact specified authority.

Example:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void deleteBook(String bookId) {
    // ...
}

@PreAuthorize("hasAuthority('book:private:read')")
public String findPrivateNotes(String bookId) {
    // ...
}
~~~

In tests, `@WithMockUser(roles = "ADMIN")` creates a user with `ROLE_ADMIN`. When an authority without a role prefix is needed, use the `authorities` attribute:

~~~java
@WithMockUser(authorities = "book:private:read")
~~~

Do not use `roles = "book:private:read"`, because Spring will automatically prepend `ROLE_` and the resulting authority will fail to match the expression.

## 6. Testing data ownership permissions

Having permission to read a category of data does not mean having permission to read every record of that type. For owner- or tenant-scoped data, check both permissions and the specific target object.

You can reference method arguments inside expressions:

~~~java
@Service
public class DocumentService {

    @PreAuthorize("@documentAuthorization.canRead(#documentId, authentication)")
    public Document findById(String documentId) {
        return documentRepository.findById(documentId)
                .orElseThrow(DocumentNotFoundException::new);
    }
}
~~~

The authorization bean can verify whether the current user has access to that exact document:

~~~java
@Component("documentAuthorization")
public class DocumentAuthorization {

    private final DocumentRepository repository;

    public DocumentAuthorization(DocumentRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(
            String documentId,
            Authentication authentication) {

        return repository.existsByIdAndOwnerUsername(
                documentId,
                authentication.getName());
    }
}
~~~

When referencing parameter names in SpEL such as `#documentId`, ensure parameter names are discoverable by Spring Security. Compile with `-parameters` or use an appropriate parameter annotation such as `@P`.

When the returned object itself must be inspected, `@PostAuthorize` can also be used:

~~~java
@PostAuthorize("returnObject.ownerUsername == authentication.name")
public Document findById(String documentId) {
    return documentRepository.findById(documentId)
            .orElseThrow(DocumentNotFoundException::new);
}
~~~

`@PostAuthorize` suits certain read operations that need to verify ownership after fetching the object. Do not use it to guard write methods, because side effects will already have occurred before the result is denied. For mutations, prefer checking authorization before making changes.

## 7. Adding Spring Security Test

To use `@WithMockUser`, `@WithAnonymousUser`, and security testing utilities, add `spring-security-test` in `test` scope.

Gradle:

~~~groovy
testImplementation("org.springframework.security:spring-security-test")
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Use Spring Boot's dependency management to select a version compatible with your active Spring Security version. You do not need to declare a version explicitly if the project already uses Spring Boot dependency management.

## 8. Testing service authorization with @WithMockUser

`@WithMockUser` populates a mock `SecurityContext` for the current test. This is a convenient way to test `@PreAuthorize`-annotated methods directly.

Example test:

~~~java
@SpringBootTest
class BookAccessServiceTests {

    @Autowired
    BookAccessService bookAccessService;

    @Test
    @WithMockUser(authorities = "book:private:read")
    void userWithPermissionCanReadPrivateNotes() {
        String notes = bookAccessService.findPrivateNotes("b-01");

        assertThat(notes)
                .contains("Internal review");
    }

    @Test
    @WithMockUser(authorities = "book:summary:read")
    void userWithoutPermissionCannotReadPrivateNotes() {
        assertThatThrownBy(() ->
                bookAccessService.findPrivateNotes("b-01"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

The first test runs with a user holding the required authority, so the method executes. The second test uses a different authority, so Spring Security throws `AccessDeniedException` before the method executes.

You must inject the real Spring-managed bean so the method security proxy takes effect. If you replace `BookAccessService` itself with a Mockito mock, the test calls the mock directly and does not test authorization proxies at all.

You can use `@WithMockUser(username = "alice", roles = "ADMIN")` to test role-based rules. For anonymous users, use `@WithAnonymousUser`.

## 9. Testing with a custom principal

`@WithMockUser` creates Spring Security's default principal. If your application requires a custom principal type, such as a `CustomUserPrincipal` carrying a tenant ID or user ID, use `@WithUserDetails` or `@WithSecurityContext`.

Example:

~~~java
@Test
@WithUserDetails("alice")
void userDetailsPrincipalCanAccessOwnedDocument() {
    Document document = documentService.findById("doc-01");

    assertThat(document.ownerUsername()).isEqualTo("alice");
}
~~~

`@WithUserDetails` uses the `UserDetailsService` in the application context to load a real user for the test. That user must exist in your test fixtures.

If the application's principal is not a `UserDetails` or requires extra claims, you can create a custom test annotation backed by `@WithSecurityContext` and `WithSecurityContextFactory`.

## 10. Distinguishing @WithMockUser from HTTP integration tests

A critical point: `@WithMockUser` places the `SecurityContext` into `SecurityContextHolder` on the thread running the test.

When a test sends an HTTP request to a server listening on a separate port, the request is handled on a different server thread. The `SecurityContext` created by `@WithMockUser` on the test thread does not automatically become the credential of that HTTP request.

Therefore:

- Use `@WithMockUser` for tests calling service methods directly or suitable in-process tests.
- For HTTP integration tests, send authentication credentials on the HTTP request, such as Basic Authentication or a bearer token.
- Never use `@WithMockUser` as proof that a real client HTTP request is authenticated.

Spring Security Test also provides testing support for WebFlux and mock requests. Still, keep a clear distinction between a test-thread mock security context and credentials sent over a real HTTP request.

When testing reactive method security directly, Spring Security Test also requires `ReactorContextTestExecutionListener` to propagate the security context into the Reactor Context. For tests using full Spring Test integration, verify that the test execution listeners are registered according to your project setup.

## 11. Configuring test users for HTTP GraphQL

Suppose the test application uses HTTP Basic and defines two users:

- `owner` with authority `book:private:read`.
- `viewer` with only authority `book:summary:read`.

A simple test configuration:

~~~java
@TestConfiguration
@EnableMethodSecurity
public class GraphQlAuthorizationTestConfiguration {

    @Bean
    UserDetailsService testUsers() {
        UserDetails owner = User.withUsername("owner")
                .password("{noop}test-password")
                .authorities("book:private:read")
                .build();

        UserDetails viewer = User.withUsername("viewer")
                .password("{noop}test-password")
                .authorities("book:summary:read")
                .build();

        return new InMemoryUserDetailsManager(owner, viewer);
    }

    @Bean
    SecurityFilterChain testSecurityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/graphql").authenticated()
                        .anyRequest().permitAll())
                .httpBasic(Customizer.withDefaults())
                .csrf(csrf -> csrf.disable())
                .build();
    }
}
~~~

`{noop}` is used solely to illustrate passwords in tests. Never use this password encoder for production accounts. The example also disables CSRF to stay focused on Basic Authentication API tests; if your application uses session cookies or browser authentication, keep CSRF protection enabled and send CSRF tokens in tests.

The configuration above assumes the test context has only one security filter chain matching the endpoint. If your application defines multiple `SecurityFilterChain` beans, verify matchers and ordering so tests run through the intended chain.

In the application itself, `@EnableMethodSecurity` must be enabled in method security configuration. Place it in application configuration rather than only in test configuration when services must be protected in production.

## 12. Testing field authorization with HttpGraphQlTester

Spring Boot can configure `HttpGraphQlTester` to call the GraphQL endpoint. Use `mutate()` to build a tester with per-user authentication headers.

Example testing an authorized user:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
@Import(GraphQlAuthorizationTestConfiguration.class)
class GraphQlAuthorizationIntegrationTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Test
    void ownerCanReadPrivateNotes() {
        HttpGraphQlTester ownerTester = graphQlTester.mutate()
                .headers(headers ->
                        headers.setBasicAuth("owner", "test-password"))
                .build();

        ownerTester.document("""
                query {
                    bookById(id: "b-01") {
                        id
                        title
                        privateNotes
                    }
                }
                """)
                .execute()
                .path("bookById.privateNotes")
                .entity(String.class)
                .isEqualTo("Internal review: verify publisher contract");
    }
}
~~~

The request travels over HTTP to the running server. The Basic Authentication header identifies the user as `owner`; the service method checks the `book:private:read` authority and grants access.

Testing an unauthorized user:

~~~java
@Test
void viewerCannotReadPrivateNotesButCanReadBook() {
    HttpGraphQlTester viewerTester = graphQlTester.mutate()
            .headers(headers ->
                    headers.setBasicAuth("viewer", "test-password"))
            .build();

    GraphQlTester.Response response = viewerTester.document("""
            query {
                bookById(id: "b-01") {
                    id
                    title
                    privateNotes
                }
            }
            """)
            .execute();

    response.errors().satisfy(errors ->
            assertThat(errors)
                    .anyMatch(error ->
                            error.getPath().contains("privateNotes")));

    response.path("bookById.id")
            .entity(String.class)
            .isEqualTo("b-01");

    response.path("bookById.privateNotes")
            .valueIsNull();
}
~~~

This test verifies three things:

1. The user can still read the public field `bookById.id`.
2. The `privateNotes` field is denied and produces a GraphQL error with the matching path.
3. The sensitive value does not appear in the data payload.

Do not check only that the response contains errors. Assert both data and paths to prove the field is protected at the exact location in the GraphQL response.

## 13. Testing HTTP 401 and 403 separately from GraphQL errors

There are two distinct authorization scenarios:

**Endpoint blocked before GraphQL execution**

If a user is not logged in and the endpoint requires authentication, Spring Security blocks the request at the HTTP layer. The response may be HTTP 401. If the user is logged in without permission to access the endpoint, the response may be HTTP 403.

Use `WebTestClient` to assert HTTP status codes directly:

~~~java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of(
                "query",
                "{ bookById(id: \"b-01\") { id } }"))
        .exchange()
        .expectStatus()
        .isUnauthorized();
~~~

This example assumes the test client sends no authentication and the endpoint requires login. In tests, inject or build a `WebTestClient` bound to the appropriate application context or server.

**A field denied during GraphQL execution**

If the endpoint permits the authenticated user, yet a specific field requires a higher authority, the GraphQL engine can still execute other fields and return a response containing both `data` and `errors`. This is where `HttpGraphQlTester.execute()` is used to inspect field paths and partial data.

Do not confuse the two outcomes:

| Scenario | Enforcement layer | How to test |
|---|---|---|
| Unauthenticated, endpoint requires login | HTTP Security | `WebTestClient` asserting 401 |
| Authenticated, not allowed to call endpoint | HTTP Security | `WebTestClient` asserting 403 |
| Allowed at endpoint, lacks authority for one field | Method Security in DataFetcher | `GraphQlTester` asserting errors and partial data |
| Has field authority, does not own object | Object-level authorization | `GraphQlTester` asserting field error and no data leak |

With HTTP-based testers, if the endpoint returns 401 or 403 before a GraphQL response is produced, `execute()` may fail because the HTTP status does not match an expected GraphQL response. When you need to assert transport status codes, use `WebTestClient` directly.

## 14. Testing authorization for Mutations

Mutations typically modify state, so authorization must be checked before executing side effects.

Example service:

~~~java
@Service
public class BookAdminService {

    @PreAuthorize("hasAuthority('book:delete')")
    public void deleteBook(String bookId) {
        bookRepository.deleteById(bookId);
    }
}
~~~

Testing an authorized user:

~~~java
@Test
@WithMockUser(authorities = "book:delete")
void userWithDeleteAuthorityCanDeleteBook() {
    bookAdminService.deleteBook("b-01");

    verify(bookRepository).deleteById("b-01");
}
~~~

Testing an unauthorized user:

~~~java
@Test
@WithMockUser(authorities = "book:read")
void userWithoutDeleteAuthorityCannotDeleteBook() {
    assertThatThrownBy(() ->
            bookAdminService.deleteBook("b-01"))
            .isInstanceOf(AccessDeniedException.class);

    verifyNoInteractions(bookRepository);
}
~~~

The second test confirms the repository was never called. That is vital proof that authorization ran before any side effects.

For mutations, test both sides:

- Unauthorized users cannot alter data.
- Authorized users succeed with the mutation and receive the expected response.

## 15. Testing authorization with GraphQlTest

`@GraphQlTest` is well suited for testing GraphQL controllers without an HTTP server. However, as a test slice, it does not automatically load all services and security configurations in the application.

If you need to test method security inside a slice test:

- Import the required method security configuration.
- Supply the real Spring-proxied service when you want annotations evaluated.
- Mock repositories or deeper dependencies rather than mocking the protected service itself.
- Ensure a security context is supplied for the execution mode in use.

Example test skeleton:

~~~java
@GraphQlTest(BookController.class)
@Import({
        MethodSecurityConfiguration.class,
        BookAccessService.class
})
class BookFieldSecuritySliceTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    @WithMockUser(authorities = "book:private:read")
    void authorizedUserCanResolvePrivateField() {
        // Arrange test fixtures, then execute the GraphQL document.
    }
}
~~~

This skeleton illustrates the slice structure; exact imports depend on your application's real constructors and dependencies. If a test requires HTTP transport security filters, `@GraphQlTest` is insufficient because it starts neither transport nor server. In that case, use a full integration test with `@SpringBootTest` and `HttpGraphQlTester`.

A common mistake is using `@MockitoBean BookAccessService` and concluding `@PreAuthorize` works. A mock replaces the Spring proxy, so that test only verifies the GraphQL controller calls the mock—it does not verify method security at all. Test service security with the real bean or a full application test.

## 16. Context propagation and SecurityContext

GraphQL Java may execute DataFetchers on a different thread from the thread that received the HTTP request. When security code relies on `SecurityContextHolder`, context propagation is critical.

Spring for GraphQL supports context propagation from the transport to the GraphQL engine and DataFetchers:

- With Spring MVC, `ThreadLocal` context from the request-handling thread can propagate to DataFetcher execution threads.
- With Spring WebFlux, the Reactor Context from the request pipeline can be used during reactive execution.
- Spring Security leverages this mechanism to supply `Authentication` for method security.

If a test shows `@PreAuthorize` working when calling the service directly yet failing during a GraphQL request, check:

1. Is method security enabled?
2. Is the invoked service a Spring-managed proxy?
3. Does the HTTP request carry valid credentials?
4. Is the test using a server-side tester, mock transport, or live HTTP server?
5. Is a reactive pipeline or custom executor dropping context?
6. Do custom thread switches preserve context propagation properly?

Never pass a username through GraphQL variables as a substitute for Authentication. Clients must never self-assert their identity inside a query; identity must come from a trusted authentication mechanism.

## 17. Preventing internal details from leaking through GraphQL errors

When authorization fails, the GraphQL response usually attaches an error to the denied field. That error informs clients and logs, but must not disclose internal details.

Avoid returning information such as:

- Stack traces.
- Table names or SQL queries.
- Internal file paths.
- Granular authorization rules that aid permission enumeration.
- Private field contents the user is not allowed to read.

You can standardize errors via `DataFetcherExceptionResolver` or `@GraphQlExceptionHandler`, depending on your exception-handling scope. Clients need only a safe message and a stable error code if your application defines one.

In tests, avoid coupling tightly to default `AccessDeniedException` messages. Instead, assert:

- An error exists at the expected field path.
- Sensitive fields are null or absent from data per schema.
- Public fields still return data when permitted.
- No sensitive details appear in error messages or extensions.

## 18. Testing the full permission matrix

An authorization test suite should cover a permission matrix rather than testing only a single successful admin case.

Example:

| User | Authority | Public query fields | `privateNotes` field | `delete` mutation |
|---|---|---|---|---|
| Anonymous | None | Blocked if endpoint requires login | Blocked | Blocked |
| Viewer | `book:summary:read` | Allowed | Denied | Denied |
| Owner | `book:private:read` | Allowed | Allowed | Denied |
| Admin | `book:private:read`, `book:delete` | Allowed | Allowed | Allowed |

The table above is an illustrative policy. Real permissions must match your application's business rules and roles/authorities.

Beyond role-based permissions, test ownership permissions:

- User A reads their own document.
- User A cannot read User B's document.
- Tenant A cannot access Tenant B's data.
- Changing IDs in GraphQL arguments cannot bypass ownership checks.

## 19. Common pitfalls when testing authorization

| Symptom | Possible cause | Resolution |
|---|---|---|
| `@PreAuthorize` has no effect | `@EnableMethodSecurity` is missing | Add method security configuration |
| Tests are always allowed | Calling a Mockito mock instead of the Spring proxy | Inject the real service bean |
| `@WithMockUser` fails over live HTTP | `SecurityContext` lives only on the test thread | Send Basic/Bearer credentials in HTTP headers |
| Authority mismatch | Confused `roles` with `authorities` | Check the `ROLE_` prefix |
| `@GraphQlTest` misses security config | Test slice does not scan general configurations | Use `@Import` or a full integration test |
| GraphQL response has null data yet test passes | Nullable field and errors were never asserted | Assert errors and field paths |
| Private field still appears | Resolver skips secured service or rule is in the wrong layer | Enforce authorization on the service method actually called |
| HTTP test gets 401 instead of GraphQL errors | Endpoint blocked before execution | Supply credentials or test HTTP status separately |
| Mutation test mutates data despite denial | Authorization ran after side effects or test hit another method | Use `@PreAuthorize` and verify repository had no interactions |
| Error message leaks details | Raw exception propagated verbatim | Standardize GraphQL error responses |

## 20. Authorization testing checklist

Before wrapping up security tests for a GraphQL API:

- [ ] Request-level security protects the right endpoint.
- [ ] Method security is enabled via `@EnableMethodSecurity`.
- [ ] Critical service methods carry `@PreAuthorize` or matching rules.
- [ ] Tests cover users with valid authorities.
- [ ] Tests cover authenticated users lacking required authorities.
- [ ] Anonymous users are tested when endpoints or fields permit anonymous access.
- [ ] Object- or tenant-level ownership is tested where needed.
- [ ] Method security tests use real Spring-managed beans.
- [ ] HTTP integration tests send credentials with requests.
- [ ] Tests distinguish HTTP 401/403 from GraphQL field errors.
- [ ] Denied fields report accurate error paths.
- [ ] Partial data conforms to schema nullability.
- [ ] Sensitive fields never appear in denied responses.
- [ ] Denied mutations cause zero side effects.
- [ ] Error messages and extensions leak no internal details.
- [ ] Context propagation works under the application's execution model.

## Conclusion

Testing authorization in Spring for GraphQL requires verifying permissions at both the HTTP endpoint and individual pieces of GraphQL data. Request-level security controls who may invoke the endpoint; method-level security with `@PreAuthorize` controls who may invoke service methods while resolving fields or executing mutations.

Use `@WithMockUser` to test service methods with the test thread's `SecurityContext`. When running HTTP integration tests with `HttpGraphQlTester`, send credentials in headers because requests run on separate server threads. Use `WebTestClient` to verify HTTP 401/403 and `GraphQlTester` to verify field errors, partial data, and the absence of leaked sensitive data.

A solid test suite proves both that authorized users succeed and that unauthorized users are rejected before any data leaks or side effects occur.

## References

- [Spring for GraphQL — Security](https://docs.spring.io/spring-graphql/reference/security.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL — Request Execution and Context Propagation](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
