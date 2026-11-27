# @PreAuthorize on resolvers

GraphQL lets clients select fields freely within an operation. Therefore, protecting the HTTP endpoint at the request level is not enough: a user may be allowed to call the endpoint yet not allowed to read a specific field, view a private book, or perform a sensitive mutation. Spring Security provides **method security** to check permissions right when a resolver is invoked. With **@PreAuthorize**, an application can set access conditions before the method handling a GraphQL field begins executing.

Spring for GraphQL uses annotated controllers to map Java methods to Queries, Mutations, Subscriptions, or field resolvers. When method security is enabled, annotations such as **@PreAuthorize** can protect these methods just like any other Spring bean method. That makes it possible to write policies based on roles, authorities, principals, and field arguments.

This lesson covers how to enable method security, apply @PreAuthorize on @QueryMapping, @MutationMapping, and @SchemaMapping, use roles/authorities and SpEL, protect nested fields, coordinate with the service layer, handle batches/subscriptions, map AccessDeniedException to GraphQL errors, and test access permissions.

## 1. Why protect resolvers?

Suppose the API has this schema:

~~~graphql
type Query {
  books: [Book!]!
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  internalNotes: String
}

type Mutation {
  deleteBook(id: ID!): Boolean!
}
~~~

A regular user can read the public book list, whereas only internal staff may view internalNotes and only administrators may delete books.

A GraphQL client can send any valid selection set in the schema. Hiding a button in the UI or omitting a field from a screen does not stop clients from sending another operation. The server must check permissions wherever data is accessed.

Example operation:

~~~graphql
query {
  book(id: "book-01") {
    id
    title
    internalNotes
  }
}
~~~

If you only protect Query.book without protecting Book.internalNotes, a user who has permission to read books can also fetch the sensitive field. Therefore, permissions must be clearly defined for every root resolver and every nested field.

## 2. Enabling method security

To use @PreAuthorize, add Spring Security and enable method security in your configuration:

~~~gradle
implementation("org.springframework.boot:spring-boot-starter-security")
~~~

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

With modern Spring Security, **@EnableMethodSecurity** enables pre/post annotations such as @PreAuthorize and @PostAuthorize by default. Older configuration using @EnableGlobalMethodSecurity has been replaced in newer versions.

Method security is implemented with Spring AOP. When a method is called through a Spring proxy, the security interceptor evaluates the expression before allowing the method to run.

Key conditions:

- The controller must be a Spring bean managed by the application context.
- The method must be invoked through the proxy so the security interceptor can execute.
- Avoid marking protected methods as private or final.
- Do not rely on self-invocation within the same bean to trigger method security.
- @EnableMethodSecurity must be enabled; merely adding @PreAuthorize does not activate this mechanism.

## 3. Distinguishing request security and method security

Spring Security can control HTTP requests in the filter chain and control method calls at the application layer.

| Mechanism | Scope | Example |
|---|---|---|
| HTTP request authorization | Entire request to the endpoint | Only logged-in users may send requests to /graphql |
| Method security | A specific method | Only users with authority book:read may call the book-reading resolver |
| Field-level authorization | A field on a GraphQL type | Only users with authority book:notes may read internalNotes |
| Domain/service authorization | A use case or resource | Users may only edit books belonging to their tenant |

A single GraphQL request can select many fields. The filter chain typically decides whether the request may enter the GraphQL endpoint; method security can allow one field while denying another field within the same operation.

Do not skip HTTP security just because @PreAuthorize is present. Authentication, CORS, CSRF, session/token validation, and request-level policies remain the responsibility of the security filter chain.

## 4. Using hasRole and hasAuthority

@PreAuthorize accepts a Spring Expression Language (SpEL) expression.

Example where only administrators can call a resolver:

~~~java
@QueryMapping
@PreAuthorize("hasRole('ADMIN')")
public List<Book> allBooks() {
    return bookService.findAll();
}
~~~

**hasRole('ADMIN')** checks the authority using the default role prefix convention, typically ROLE_ADMIN.

If the application uses specific authorities, you can check them explicitly:

~~~java
@QueryMapping
@PreAuthorize("hasAuthority('book:read')")
public List<Book> books() {
    return bookService.findPublicBooks();
}
~~~

**hasAuthority('book:read')** performs an exact match against the authority string granted to Authentication.

Examples:

| Expression | Authority checked |
|---|---|
| hasRole('ADMIN') | ROLE_ADMIN using the default role prefix |
| hasAuthority('ROLE_ADMIN') | ROLE_ADMIN |
| hasAuthority('book:read') | book:read |
| hasAnyAuthority('book:read', 'book:admin') | Has at least one listed authority |
| isAuthenticated() | Has an authenticated principal |
| isAnonymous() | Request is being processed as anonymous |

Choose a consistent role and permission convention. Roles usually represent broad groups of responsibilities; authorities can represent specific actions on resources.

## 5. Protecting @QueryMapping

Example where only users with book-read permission can call the query:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('book:read')")
    public List<Book> books() {
        return bookService.findVisibleBooks();
    }

    @QueryMapping
    @PreAuthorize("hasRole('ADMIN')")
    public List<Book> allBooks() {
        return bookService.findAll();
    }
}
~~~

When a user lacks the book:read authority, Spring Security rejects the method before calling bookService.findVisibleBooks().

Protecting the method avoids repeating permission checks across branches inside the resolver. However, if permissions depend on each specific book or tenant, checking a general authority alone may not suffice; resource-specific policies must be checked in a service or authorization component.

## 6. Protecting @MutationMapping

Mutations usually modify data, so they need explicit permission policies.

~~~java
@MutationMapping
@PreAuthorize("hasAuthority('book:delete')")
public boolean deleteBook(@Argument String id) {
    bookService.delete(id);
    return true;
}
~~~

Only users with the book:delete authority may call the method.

If permission depends on a specific book, you can call a permission-checking bean inside SpEL:

~~~java
@MutationMapping
@PreAuthorize("@bookAuthorization.canDelete(#id, authentication)")
public boolean deleteBook(@Argument("id") String id) {
    bookService.delete(id);
    return true;
}
~~~

The bookAuthorization bean can check ownership, tenant, or business policy. The condition is evaluated before the deleteBook method executes.

Example component:

~~~java
@Component("bookAuthorization")
public class BookAuthorization {

    private final BookRepository bookRepository;

    public BookAuthorization(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    public boolean canDelete(String bookId, Authentication authentication) {
        return bookRepository.findById(bookId)
                .filter(book -> book.getOwnerUsername()
                        .equals(authentication.getName()))
                .isPresent();
    }
}
~~~

In multi-tenant applications, policies must check both tenant and actor. Never trust a client-supplied tenant ID if it has not been verified against the principal.

## 7. Using method arguments in SpEL

@PreAuthorize can reference method parameters. For example:

~~~java
@QueryMapping
@PreAuthorize("@bookAuthorization.canRead(#id, authentication)")
public Book book(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

Here #id is the Java parameter value bound from the GraphQL argument. Spring Security needs to determine parameter names to resolve SpEL variables.

For the #id expression to work reliably:

- Compile Java with the -parameters option to retain parameter names, or
- Use the parameter-naming annotation supported by Spring Security, such as @P("id"), or
- Use positional parameter references such as #p0 if that fits the project's convention.

Example using @P:

~~~java
@QueryMapping
@PreAuthorize("@bookAuthorization.canRead(#bookId, authentication)")
public Book book(
        @Argument("id") @P("bookId") String id) {
    return bookService.findById(id);
}
~~~

The GraphQL argument name and the SpEL parameter name are two separate concepts. @Argument("id") tells Spring GraphQL to take the value from the input field id; @P("bookId") names the method parameter variable for SpEL to reference.

Never concatenate user input into a SpEL expression. Expressions should be statically declared in source code; GraphQL data should only be passed via method parameters.

## 8. Using principal and authentication in SpEL

SpEL provides variables and functions related to the current user:

~~~java
@QueryMapping
@PreAuthorize("isAuthenticated()")
public List<Book> myBooks(Authentication authentication) {
    return bookService.findOwnedBy(authentication.getName());
}
~~~

You can use the principal in an expression:

~~~java
@QueryMapping
@PreAuthorize("authentication.name == #username")
public List<Book> booksForUser(@Argument String username) {
    return bookService.findOwnedBy(username);
}
~~~

However, letting the client pass a username and merely comparing it to the principal is usually unnecessary. For queries like myBooks, it is better to retrieve the actor from Authentication inside the resolver/service and not let the client choose a username.

Example:

~~~java
@QueryMapping
@PreAuthorize("isAuthenticated()")
public List<Book> myBooks(Authentication authentication) {
    return bookService.findOwnedBy(authentication.getName());
}
~~~

For tenant or organization information, retrieve it from the principal or a trusted tenant resolver and check permissions before querying.

## 9. Protecting nested fields with @SchemaMapping

A root query can return Book, after which GraphQL resolves child fields. To protect a sensitive field, create an explicit resolver and place @PreAuthorize on that method.

~~~java
@Controller
public class BookFieldController {

    @SchemaMapping(typeName = "Book", field = "internalNotes")
    @PreAuthorize("hasAuthority('book:notes:read')")
    public String internalNotes(Book book) {
        return book.getInternalNotes();
    }
}
~~~

Schema:

~~~graphql
type Book {
  id: ID!
  title: String!
  internalNotes: String
}
~~~

Clients can read title, but cannot read internalNotes if they lack the book:notes:read authority.

### Why is an explicit resolver needed?

GraphQL can use a default property fetcher to read values from a property or getter on the source object. If a field is resolved directly from a property without calling a security-proxied controller/service method, the @PreAuthorize annotation never gets a chance to run.

For sensitive fields:

1. Declare an explicit resolver using @SchemaMapping or an appropriate DataFetcher.
2. Place method security on a method invoked through a Spring proxy.
3. Check permissions before returning data.
4. Never rely on the client not selecting the field in the UI.

This is why field-level authorization must be designed alongside the schema and resolvers.

## 10. Distinguishing permissions at root fields and nested fields

Example:

~~~graphql
query {
  book(id: "book-01") {
    id
    title
    internalNotes
  }
}
~~~

The Query.book resolver may require book:read, whereas Book.internalNotes requires book:notes:read.

| Field | Example policy | Meaning |
|---|---|---|
| Query.book | book:read | Allowed to read book information |
| Book.title | book:read or public | Allowed to view title |
| Book.internalNotes | book:notes:read | Allowed to view internal notes |
| Mutation.deleteBook | book:delete | Allowed to delete book |

An operation can succeed partially. For instance, Query.book is allowed while the nested field internalNotes is denied. The GraphQL response can retain permitted fields in data and add an error at the path of internalNotes.

If the schema declares a sensitive field as non-null, an authorization error can bubble null up to the parent object. Design nullability based on semantics and behavior when a field is denied.

## 11. Protecting data per resource with an authorization bean

General roles or authorities are not enough for every case. For example, a user has the book:update permission but may only update books they own.

You can encapsulate the policy in a bean:

~~~java
@Component("bookAuthorization")
public class BookAuthorization {

    private final BookRepository repository;

    public BookAuthorization(BookRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(String bookId, Authentication authentication) {
        return repository.findById(bookId)
                .filter(book -> book.isPublic()
                        || book.getOwnerUsername()
                                .equals(authentication.getName()))
                .isPresent();
    }

    public boolean canUpdate(String bookId, Authentication authentication) {
        return repository.findById(bookId)
                .filter(book -> book.getOwnerUsername()
                        .equals(authentication.getName()))
                .isPresent();
    }
}
~~~

Use in a resolver:

~~~java
@MutationMapping
@PreAuthorize("@bookAuthorization.canUpdate(#id, authentication)")
public Book updateBook(
        @Argument String id,
        @Argument UpdateBookInput input) {
    return bookService.update(id, input);
}
~~~

An authorization bean should contain clear, easily testable policies. Avoid overly long expressions or embedding complex database queries directly in annotations.

If a policy requires substantial data or operations with side effects, implement it in the service/domain layer instead of calling complex methods from SpEL.

## 12. Combining @PreAuthorize with service-layer security

Protecting resolvers expresses permissions at GraphQL fields. However, a service may be called from a REST API, scheduled job, message listener, or another use case. Therefore, important business rules should also be protected at the service/application layer.

Example:

~~~java
@Service
public class BookService {

    @PreAuthorize("hasAuthority('book:delete')")
    public void delete(String bookId) {
        bookRepository.deleteById(bookId);
    }
}
~~~

Resolver:

~~~java
@MutationMapping
public boolean deleteBook(@Argument String id) {
    bookService.delete(id);
    return true;
}
~~~

Method security on the service protects the use case regardless of whether it is called from GraphQL or another adapter.

You can keep @PreAuthorize on a resolver if a GraphQL-specific policy is needed, such as restricting a field or operation. Avoid duplicating identical expressions everywhere without reason; establish the authoritative policy at the service layer and use resolvers to control field-specific behavior.

### Self-invocation note

Method security relies on proxies. If a method in the same bean directly calls another method via this.method(), that internal call can bypass the proxy and skip the target method's @PreAuthorize.

Extract protected use cases into a separate Spring bean or invoke them through a properly managed proxy. Do not treat the annotation as an automatic check for all internal calls.

## 13. @PostAuthorize and result-based permissions

@PreAuthorize checks before the method runs. When a policy depends on the returned object, you can use **@PostAuthorize**:

~~~java
@QueryMapping
@PostAuthorize(
        "returnObject == null || " +
        "returnObject.ownerUsername == authentication.name")
public Book book(@Argument String id) {
    return bookService.findById(id);
}
~~~

@PostAuthorize evaluates after the method returns. This is useful when checking the owner of a newly loaded object.

However, keep in mind:

- Data has already been loaded before the policy is evaluated.
- Do not use @PostAuthorize to replace tenant query filters in the database.
- Avoid returning sensitive objects from a service and checking afterward if there is a risk of side effects or leakage via logs/caches.
- For collections, @PostAuthorize does not automatically filter individual elements like a query policy.

Whenever possible, filter data by actor/tenant directly in the repository/service and use @PreAuthorize to verify permission to invoke the use case.

## 14. @PreAuthorize on @BatchMapping

A @BatchMapping receives multiple source objects at once. @PreAuthorize on a batch method can check general permission to invoke the batch handler:

~~~java
@BatchMapping(typeName = "Book", field = "internalNotes")
@PreAuthorize("hasAuthority('book:notes:read')")
public Map<Book, String> internalNotes(List<Book> books) {
    return bookService.loadInternalNotes(books);
}
~~~

However, a general authority does not automatically check permissions on each individual Book. If users are only allowed to view notes for certain books, the batch handler or service must apply per-source-object policies.

Example:

~~~java
@BatchMapping(typeName = "Book", field = "internalNotes")
@PreAuthorize("isAuthenticated()")
public Map<Book, String> internalNotes(
        List<Book> books,
        Authentication authentication) {

    return bookService.loadReadableNotes(books, authentication);
}
~~~

The service must determine which books the current principal is allowed to read and build the result accordingly for each source. Do not assume @PreAuthorize on a batch method runs once per Book; the method is called per batch.

## 15. @PreAuthorize on Subscription resolvers

A Subscription resolver is called when the client establishes the stream. You can use @PreAuthorize to check permission to open the subscription:

~~~java
@SubscriptionMapping
@PreAuthorize("hasAuthority('order:events:read')")
public Flux<OrderEvent> orderEvents(@Argument String orderId) {
    return orderEventService.eventsFor(orderId);
}
~~~

Method security checks the call that creates the Publisher. For long-lived streams, do not assume permissions are re-checked every time an event is emitted. If permissions can be revoked while the stream is open, the event source or pipeline needs a mechanism to re-check or terminate the stream.

For sensitive data, verify all of the following:

- Whether the user has permission to subscribe to the resource.
- Whether each event still falls within the scope the user is allowed to view.
- Whether the tenant and principal remain valid throughout the stream lifecycle.
- Whether cancellation releases listeners when the client disconnects.

## 16. Authentication context in MVC and WebFlux

Spring Security provides Authentication to method security. In Servlet/MVC applications, the security context is typically accessed via SecurityContextHolder following Servlet stack context mechanics.

In WebFlux, Spring Security uses Reactor Context to propagate SecurityContext along the reactive pipeline. Do not rely on ThreadLocal or assume a request always runs on the same thread.

When a resolver returns Mono/Flux or performs asynchronous work:

- Keep the reactive chain managed by the framework.
- Do not switch arbitrarily to another thread and read SecurityContextHolder as if still in the same context.
- Use the appropriate reactive security context mechanism when obtaining Authentication inside the pipeline.
- Test against the actual web stack your application deploys.

Reactive method security requires configuration tailored to reactive applications; Spring Security provides @EnableReactiveMethodSecurity for reactive method security. Do not mix reactive and Servlet configurations arbitrarily in the same application.

## 17. Handling AccessDeniedException in GraphQL

When @PreAuthorize denies a resolver, Spring Security can throw **AccessDeniedException**. Because the exception arises while GraphQL is resolving a field, it is handled within GraphQL execution and can become a GraphQL error.

You can use @GraphQlExceptionHandler to standardize the response:

~~~java
@ControllerAdvice
public class GraphQlSecurityExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleAccessDenied(
            AccessDeniedException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.FORBIDDEN)
                .message("You do not have permission to access this field")
                .extensions(Map.of("code", "FORBIDDEN"))
                .build();
    }
}
~~~

The handler should only return safe information. Do not include role names, authorities, SpEL expressions, or internal policy details in messages returned to clients.

Distinguish two cases:

- Request rejected by a security filter before GraphQL execution starts: typically handled as HTTP 401/403 at the transport/security layer.
- Resolver rejected by method security during GraphQL execution: typically represented in GraphQL response errors, including the path to the affected field.

If an operation selects multiple fields, one denied field does not necessarily wipe out all data. The outcome also depends on the nullability of the field and parent fields in the schema.

## 18. Field authorization and nullability

Schema:

~~~graphql
type Book {
  id: ID!
  title: String!
  internalNotes: String
}
~~~

internalNotes is nullable. If a user is not allowed to view this field, GraphQL can return null for the field and include an error.

If the schema declares:

~~~graphql
type Book {
  id: ID!
  internalNotes: String!
}
~~~

When a non-null field resolver is denied and returns an error, GraphQL cannot keep null at that field. Null can bubble up to the Book object and continue bubbling through non-null parent fields.

Therefore, when designing sensitive fields:

- Choose nullability aligned with semantics and potential authorization failures.
- Verify partial data in responses.
- Never turn denied access into fake default values.
- Consider hiding the field or returning the same response for not found/forbidden if avoiding disclosure of resource existence.

## 19. Testing @PreAuthorize on resolvers

You can use **@WithMockUser** to test with a mock Authentication and **GraphQlTester** to send operations.

Example of an authorized user:

~~~java
@SpringBootTest
class BookResolverSecurityTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    @WithMockUser(authorities = "book:read")
    void shouldAllowBookQuery() {
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
            .entityList(Book.class)
            .hasSize(1);
    }
}
~~~

The example assumes the test fixture already contains one book.

Example of a user lacking permission:

~~~java
@Test
@WithMockUser(authorities = "book:write")
void shouldRejectBookQuery() {
    graphQlTester.document("""
            query {
                books {
                    id
                    title
                }
            }
            """)
        .execute()
        .errors()
        .expect()
        .message("You do not have permission to access this field")
        .verify();
}
~~~

The test above assumes the application has a @GraphQlExceptionHandler mapping AccessDeniedException to the message as in the previous example.

You should test:

1. Users with the authority are allowed to call the resolver.
2. Users lacking the authority are denied before the service is called.
3. hasRole and hasAuthority match the expected convention.
4. SpEL references the correct argument name.
5. Resource owners are allowed, others are denied.
6. Sensitive nested fields are blocked even when the root query is allowed.
7. Aliases and nested selections still produce accurate error paths.
8. Mutations perform no side effects when denied.
9. Batch mappings check permissions per source when required.
10. Subscriptions check permissions when opening the stream and per event if policy requires.
11. Reactive resolvers preserve the Authentication context.
12. Requests blocked at the filter chain are distinguished from field errors in GraphQL responses.

For integration tests over HTTP, use the tester matching the transport to verify the filter chain, CSRF, authentication headers/cookies, and response status. GraphQlTester at the execution layer focuses on GraphQL execution and does not by itself verify all HTTP security configurations.

## 20. Common issues when protecting resolvers

| Symptom | Possible cause | Solution |
|---|---|---|
| @PreAuthorize does not run | @EnableMethodSecurity not enabled | Enable method security in configuration |
| Valid role is still denied | Wrong ROLE_ prefix or wrong string in hasAuthority | Check actual authorities and choose hasRole/hasAuthority |
| SpEL cannot find #id | Parameter names not retained or declared | Enable -parameters, use @P, or use #p0 |
| Root query protected but nested field still leaks | Field uses default property fetcher | Create an explicit resolver and apply method security |
| Annotated service method does not run checks | Self-invocation bypasses proxy | Extract method to another bean or invoke via proxy |
| User with general permission reads all resources | Only authority checked, missing ownership/tenant policy | Check resource in authorization bean/service |
| Batch mapping only checks once | Misunderstanding that @PreAuthorize runs per source | Check per-object policy inside the batch service |
| Subscription keeps sending data after revoke | Permissions only checked when creating Publisher | Recheck per event or terminate stream |
| AccessDenied leaks internal details | Exception message or expression returned | Map to public message/code |
| Field null bubbles up to parent | Non-null propagation | Review nullability and error handling |
| Reactive resolver loses security context | Relied on ThreadLocal or lost Reactor Context | Use reactive security context propagation |
| Test reports denied despite correct method | Mock user missing authority or test context not set up | Check @WithMockUser and test stack |

## 21. Workflow for implementing @PreAuthorize on resolvers

When protecting GraphQL fields:

1. List fields and mutations in the schema that require protection.
2. Define policies: role, authority, ownership, tenant, or domain state.
3. Add Spring Security and enable @EnableMethodSecurity.
4. Place @PreAuthorize on appropriate @QueryMapping, @MutationMapping, or @SchemaMapping methods.
5. Use hasRole for roles and hasAuthority for specific permissions.
6. Reference method arguments in SpEL only when parameter names are reliably resolved by Spring Security.
7. Use authorization beans for resource-level policies; avoid overly complex expressions.
8. Create explicit resolvers for sensitive fields instead of relying on default property fetchers.
9. Place critical business rules in the service layer to protect other entry points.
10. For batches and subscriptions, check permissions per resource or per event when needed.
11. Standardize AccessDeniedException into safe GraphQL errors.
12. Test allowed permissions, denied permissions, nested fields, mutation side effects, and transport security.

@PreAuthorize on resolvers enables checking permissions right before Spring for GraphQL executes a field or operation. Method security must be enabled with @EnableMethodSecurity and methods must be invoked through a Spring proxy. Combine roles/authorities with resource-level policies, protect nested fields with explicit resolvers, and keep domain rules in the service layer. For batches or subscriptions, a single method check does not replace per-object/per-event authorization. Finally, standardize AccessDeniedException into safe GraphQL errors and test both partial data and side effects to ensure clients only receive authorized data.
