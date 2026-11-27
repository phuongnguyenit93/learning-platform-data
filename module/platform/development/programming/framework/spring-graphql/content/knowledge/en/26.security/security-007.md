# Argument-based authorization

GraphQL fields often accept data sent by the client via arguments. For example, bookById(id: ID!), ordersByCustomer(customerId: ID!), or updateBook(input: UpdateBookInput!). These arguments tell the resolver which resource the client wants to access, but **do not prove the client is authorized to access that resource**.

If the server simply loads data by ID without checking ownership, tenant, or specific permissions, the API may suffer from Broken Object Level Authorization (BOLA), commonly known as IDOR. A user swapping IDs in a query could read or modify someone else's data.

In Spring for GraphQL, argument-based authorization typically combines @Argument or @Arguments to bind values, Spring Security method security to protect methods, and an authorization service to check permissions by principal, resource, and tenant. Rules must be enforced at the application/domain layer so every entry point shares the same policy.

## 1. Arguments are neither identity nor access rights

Consider the schema:

~~~graphql
type Query {
    orderById(id: ID!): Order
}
~~~

A client can send:

~~~graphql
query {
    orderById(id: "order-9001") {
        id
        total
    }
}
~~~

id is merely the identifier of the resource the client wants to read. The server must obtain the principal from a verified authentication mechanism, then check whether that principal is allowed to read that order.

Do not write logic such as:

~~~java
// Unsafe: the client-supplied ID is used directly to return data.
@QueryMapping
public Order orderById(@Argument("id") UUID id) {
    return orderRepository.findById(id).orElse(null);
}
~~~

If IDs are guessable or obtainable from another response, users can access orders they have no rights to. Hard-to-guess IDs do not replace authorization either.

A secure rule must combine:

- **Principal:** who the authenticated caller is.
- **Action:** what the caller wants to do, e.g. read, update, or cancel.
- **Resource:** the specific object indicated by the argument.
- **Context:** tenant, organization, ownership, resource state, and relevant policies.

This is attribute-based authorization (ABAC): permission decisions based on attributes of the subject, action, resource, and execution environment. General roles/authorities remain useful, but are often insufficient to decide access to a specific object.

## 2. Receiving arguments in annotated controllers

Spring for GraphQL provides @Argument to bind a named argument to a Java parameter:

~~~graphql
type Query {
    bookById(id: ID!): Book
}
~~~

~~~java
@QueryMapping
public Book bookById(@Argument("id") UUID bookId) {
    return bookService.findById(bookId);
}
~~~

With an input object:

~~~graphql
input UpdateBookInput {
    bookId: ID!
    title: String
    description: String
}

type Mutation {
    updateBook(input: UpdateBookInput!): Book
}
~~~

~~~java
public record UpdateBookInput(
        UUID bookId,
        String title,
        String description) {
}

@MutationMapping
public Book updateBook(@Argument("input") UpdateBookInput input) {
    return bookService.update(input);
}
~~~

@Arguments can bind all arguments of a field into a DTO or Map. Regardless of how they are received, the data remains client-controlled. Successful binding, matching types, and valid input validation do not mean the caller is permitted to read or modify the specified resource.

GraphQL applies variable coercion, default values, and nullability according to the schema before the resolver processes arguments. When authorization depends on whether an input field was omitted versus explicitly passed as null, preserve that distinction, for example using ArgumentValue<T> in an appropriate DTO.

## 3. Enabling method security

To use @PreAuthorize, the application must enable method security:

~~~java
@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {
}
~~~

For reactive applications, configure reactive method security accordingly using @EnableReactiveMethodSecurity and ensure the security context is propagated in the Reactor Context.

Method security uses Spring AOP to intercept calls to protected beans. Methods must be called through the Spring proxy; self-invocation inside the same object can bypass the interceptor. Therefore, placing rules on a service bean injected via constructor and invoked through a proxy is easy to reason about and control.

## 4. Checking permissions by ID with @PreAuthorize

You can protect a resolver with @PreAuthorize and invoke an authorization bean via SpEL. Example:

~~~java
@Component("bookAuthorization")
public class BookAuthorization {

    private final BookAccessRepository accessRepository;

    public BookAuthorization(BookAccessRepository accessRepository) {
        this.accessRepository = accessRepository;
    }

    public boolean canRead(Authentication authentication, UUID bookId) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        return accessRepository.existsReadableBook(
            bookId, authentication.getName());
    }
}
~~~

Resolver:

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    @PreAuthorize("@bookAuthorization.canRead(authentication, #p0)")
    public Book bookById(@Argument("id") UUID bookId) {
        return bookService.findById(bookId);
    }
}
~~~

#p0 references the first method parameter. If you want a more readable expression, you can name the method parameter clearly and use #bookId; in that case, ensure Spring can discover parameter names, usually via the -parameters compiler option. Spring Security also supports the @P annotation to name parameters used in expressions:

~~~java
@QueryMapping
@PreAuthorize("@bookAuthorization.canRead(authentication, #bookId)")
public Book bookById(
        @Argument("id")
        @P("bookId") UUID id) {
    return bookService.findById(id);
}
~~~

@Argument("id") names the GraphQL argument; @P("bookId") names the parameter for method security. These two names serve two different mechanisms.

The authorization component must verify real permissions against trusted data, such as ownership or membership. Never merely compare an ID against another argument sent by the same client and treat that as proof of authorization.

## 5. Placing authorization in the application service

Protecting resolvers can stop calls early, but business rules should reside at the service/domain boundary so REST controllers, message consumers, scheduled jobs, and GraphQL share the same policy.

Example:

~~~java
@Service
public class BookQueryService {

    private final BookRepository bookRepository;

    public BookQueryService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @PreAuthorize("@bookAuthorization.canRead(authentication, #p0)")
    public Book findVisibleById(UUID bookId) {
        return bookRepository.findVisibleById(
                bookId, SecurityContextHolder.getContext()
                    .getAuthentication().getName())
            .orElseThrow(BookNotFoundException::new);
    }
}
~~~

In real code, avoid retrieving SecurityContext manually if the service runs reactively. You can pass the authenticated principal/user scope into the service explicitly, or use the method security mechanism matching your stack. The goal is never to take user identity from client arguments.

The controller simply passes the bound data:

~~~java
@QueryMapping
public Book bookById(@Argument("id") UUID bookId) {
    return bookQueryService.findVisibleById(bookId);
}
~~~

If a service can be called from multiple places, placing authorization on the service reduces the risk that a new entry point forgets to check permissions. You can add method security on resolvers as an early defense layer, but critical policies should not exist solely in controllers.

## 6. Authorizing by tenant argument

A multi-tenant API might accept a tenant ID:

~~~graphql
type Query {
    booksByTenant(tenantId: ID!): [Book!]!
}
~~~

Never trust a client-supplied tenantId. The server must verify that the current principal has membership or an appropriate role in that tenant:

~~~java
@Component("tenantAuthorization")
public class TenantAuthorization {

    private final TenantMembershipRepository membershipRepository;

    public TenantAuthorization(
            TenantMembershipRepository membershipRepository) {
        this.membershipRepository = membershipRepository;
    }

    public boolean canRead(Authentication authentication, UUID tenantId) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }
        return membershipRepository.existsActiveMembership(
            authentication.getName(), tenantId, "BOOK_READ");
    }
}
~~~

~~~java
@QueryMapping
@PreAuthorize("@tenantAuthorization.canRead(authentication, #p0)")
public List<Book> booksByTenant(@Argument("tenantId") UUID tenantId) {
    return bookService.findByTenant(tenantId);
}
~~~

In some systems, the current tenant is selected in the session/token and clients do not need to pass a tenant ID on every field. If the API allows clients to switch tenants, the server must still verify membership for every operation.

When querying the database, scope queries by the authenticated tenant instead of loading everything and filtering in Java. For example, the repository should accept both tenantId and resource ID so the query only returns records belonging to the permitted tenant. This reduces data-leak risks and avoids loading unauthorized data into memory.

## 7. Authorization with mutation input objects

Mutations typically receive an input object containing the resource ID and fields to modify. The server must check permissions on the target resource before performing side effects:

~~~java
public record UpdateBookInput(
        UUID bookId,
        String title,
        String description) {
}

@Service
public class BookCommandService {

    private final BookRepository bookRepository;

    public BookCommandService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional
    @PreAuthorize("@bookAuthorization.canEdit(authentication, #p0.bookId())")
    public Book update(UpdateBookInput input) {
        Book book = bookRepository.findEditableById(input.bookId())
            .orElseThrow(BookNotFoundException::new);

        if (input.title() != null) {
            book.rename(input.title());
        }
        if (input.description() != null) {
            book.changeDescription(input.description());
        }
        return bookRepository.save(book);
    }
}
~~~

In SpEL, record components can be accessed via property/accessor syntax. If the expression cannot resolve component names under the current configuration, use the appropriate accessor or pass the resource ID separately to the service method so the expression stays clear.

Only allow updating fields that belong to the contract. Never bind an entire entity directly and save it, because the input could contain fields like ownerId, tenantId, role, or isPublished that clients must not set themselves. This is the mass assignment risk.

For mutations, authorization must happen before side effects. Never use @PostAuthorize as the sole protection layer for write operations, because that annotation checks after the method has already run and side effects may have committed.

## 8. Authorization across multiple arguments

A field may receive multiple arguments that jointly affect the permission decision:

~~~graphql
type Query {
    invoice(
        tenantId: ID!
        invoiceId: ID!
        includeAudit: Boolean = false
    ): Invoice
}
~~~

The policy may need to verify that the principal belongs to the tenant, that the invoice belongs to that tenant, and that the caller has permission to read audit data if includeAudit is true.

~~~java
@QueryMapping
public Invoice invoice(
        @Argument("tenantId") UUID tenantId,
        @Argument("invoiceId") UUID invoiceId,
        @Argument("includeAudit") boolean includeAudit,
        Principal principal) {

    return invoiceQueryService.findVisibleInvoice(
        principal.getName(), tenantId, invoiceId, includeAudit);
}
~~~

The service should enforce all conditions within a single policy:

~~~java
public Invoice findVisibleInvoice(
        String username,
        UUID tenantId,
        UUID invoiceId,
        boolean includeAudit) {

    authorization.requireTenantMembership(username, tenantId);
    Invoice invoice = repository.findByIdAndTenant(invoiceId, tenantId)
        .orElseThrow(InvoiceNotFoundException::new);
    authorization.requireCanReadInvoice(username, invoice);

    if (includeAudit) {
        authorization.requireAuditAccess(username, tenantId);
    }
    return invoice;
}
~~~

The example above passes the authenticated principal from Spring Security into the service. Never replace username with a client-supplied userId argument. If a field has many arguments, a DTO bound via @Arguments or an input object can keep method signatures clean, while the policy still checks every attribute affecting permissions.

## 9. Authorization for nested fields

GraphQL allows nested fields to accept their own arguments:

~~~graphql
type Book {
    id: ID!
    reviews(visibility: ReviewVisibility = PUBLIC): [Review!]!
}
~~~

The Book.reviews resolver must check permissions based on the source Book object and the visibility argument. Users must not be able to request INTERNAL visibility merely because the schema permits that enum value:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
@PreAuthorize("@reviewAuthorization.canRead(authentication, #p0.id(), #p1)")
public List<Review> reviews(
        Book book,
        @Argument("visibility") ReviewVisibility visibility) {

    return reviewService.findVisibleReviews(book.id(), visibility);
}
~~~

In the method security expression, #p0 is the first source object parameter and #p1 is the second argument according to Java parameter order. You can name them explicitly with @P to avoid relying on parameter metadata. Even though the source object was resolved by the server, permissions still need checking because parent data may be reached through multiple paths.

A nested field may be invoked multiple times in the same operation with different arguments. Each resolution must be authorized against the corresponding source object and arguments.

## 10. Aliases and the same field with multiple arguments

GraphQL allows calling the same field multiple times using aliases:

~~~graphql
query {
    ownBook: bookById(id: "book-01") {
        id
        title
    }
    anotherBook: bookById(id: "book-02") {
        id
        title
    }
}
~~~

Two aliases produce two response keys and can trigger two resolutions with different arguments. Do not check permissions once per operation and assume all subsequent calls to the same field are permitted. Authorization must be tied to the actual resource ID on each invocation.

Similarly, do not cache authorization decisions solely by field name or role if the decision also depends on resource ID, tenant, or other arguments. If caching policy decisions, keys must include all attributes affecting the decision and TTLs must match permission-change requirements.

## 11. Combining role-based and attribute-based authorization

Roles/authorities can check general permissions:

~~~java
@PreAuthorize("hasAuthority('books:read')")
~~~

Yet permission to read a book may also depend on ownership, tenant, or status:

~~~java
@PreAuthorize("""
    hasAuthority('books:read')
    and @bookAuthorization.canRead(authentication, #p0)
    """)
~~~

This combines RBAC and ABAC:

- RBAC checks whether the principal holds the general authority.
- ABAC checks whether the specific resource falls within the principal's scope.

Do not cram complex logic into a long SpEL expression. Place policies in a dedicated component so they are easy to test, audit, and reuse. SpEL should invoke the policy, not contain dozens of data query conditions.

## 12. DataLoader and key-based authorization

DataLoader batches keys to reduce N+1 queries. However, a batch loader must never skip authorization just because it receives many IDs in a single call.

For example, a Book.author field uses DataLoader to load authors by ID. The batch query must only return authors the current principal is allowed to view. If data depends on tenant, the batch loader must receive a trusted tenant scope from the security/GraphQL context and apply that condition across the entire query.

Never use a client-supplied tenantId directly as the scope for caches or batch queries. Derive the tenant from the authenticated principal or verify membership before using it.

DataLoader caches are typically scoped to a single GraphQL execution/request. However, keying solely by author ID may be insufficient if results depend on tenant or policy. In that case, ensure a single execution has one consistent security scope or use a key containing all attributes affecting the result. Never share DataLoader instances/caches across principals.

Field-level authorization must also apply to nested fields loaded via DataLoader. You can filter data directly in the batch query or check permissions before returning values. Avoid loading unauthorized sensitive data into the resolver and hoping the client does not select that field.

## 13. Async and reactive authorization

Resolvers can return CompletableFuture, Mono, or Flux. When method security is used, configure it properly for imperative or reactive stacks:

- With Spring MVC/imperative, method security typically relies on the current SecurityContext.
- With WebFlux/reactive, SecurityContext is propagated via Reactor Context.
- When switching manually to executors or CompletableFuture, do not assume ThreadLocal automatically follows to other threads.

Reactive service example:

~~~java
@PreAuthorize("hasAuthority('books:read')")
public Mono<Book> findVisibleBook(UUID bookId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(authentication ->
            bookRepository.findVisibleById(
                bookId, authentication.getName()));
}
~~~

This illustrates reading the security context inside a reactive chain. If the method is protected with reactive method security, let the framework enforce authorization and keep all operations inside publishers; never call block() to obtain the principal or permission result.

With CompletableFuture, pass the authenticated user scope into async tasks explicitly or configure appropriate context propagation. Never store Authentication in static variables or mutable singleton fields for async callbacks to read later.

## 14. Authorization for subscription arguments

Subscriptions also accept arguments, such as orderUpdated(orderId: ID!). Before opening the stream, the server must verify the principal is permitted to watch that order:

~~~java
@SubscriptionMapping
public Flux<OrderEvent> orderUpdated(
        @Argument("orderId") UUID orderId,
        Principal principal) {

    String username = principal.getName();
    return orderAuthorization.assertCanReadOrder(username, orderId)
        .thenMany(orderEventService.eventsForOrder(orderId));
}
~~~

For sensitive streams or permissions that can change, checking only at subscribe time is insufficient. Filter per event or integrate revocation signals to terminate the stream. Never use a client-supplied orderId or tenant ID to subscribe to a topic without verifying permissions first.

## 15. Forbidden or Not Found?

When a resource exists but the caller lacks permission, the API can return FORBIDDEN. However, in some systems, distinguishing a non-existent resource from an existing forbidden resource can leak information.

Two common policies:

| Policy | Behavior | When appropriate |
| --- | --- | --- |
| Distinguish NOT_FOUND and FORBIDDEN | Client knows whether the resource does not exist or access is denied | Non-sensitive resources where the product needs the distinction |
| Conceal existence | Return NOT_FOUND or a generic message for both cases | Sensitive resources requiring anti-enumeration protection |

Choose one consistent policy and map it with stable GraphQL error codes. Do not let error messages or timing accidentally leak information the policy intends to hide.

## 16. @PostAuthorize and its limitations

@PostAuthorize checks the result after the method executes. It can be useful for some queries when permission depends on the returned object:

~~~java
@PostAuthorize("@bookAuthorization.canRead(authentication, returnObject)")
public Book loadBook(UUID bookId) {
    return repository.findById(bookId).orElseThrow();
}
~~~

However, the method has already loaded the object before the check. This may be inappropriate if loading triggered side effects, wrote audit entries, accessed sensitive systems, or leaked data via logs/caches. For mutations, @PostAuthorize cannot undo side effects that have already executed.

Prefer @PreAuthorize when permissions can be checked from IDs/arguments before calling the service. If a resource must be loaded to inspect attributes needed for checking, perform the check inside the service/domain before returning the object or mutating data, while ensuring queries only read within an appropriate scope.

## 17. Testing argument-based authorization

Testing must cover both allowed and denied cases. Testing only unauthenticated users is insufficient; BOLA bugs typically happen when an authenticated user swaps an ID or tenant in arguments.

With GraphQlTester, send operations and assert data for the appropriate principal:

~~~java
graphQlTester.document("""
        query($id: ID!) {
            bookById(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-01")
    .execute()
    .path("bookById.id")
    .entity(String.class)
    .isEqualTo("book-01");
~~~

Tests must be configured with an authenticated principal. For integration tests over HTTP, use the security test support for your active stack, such as MockMvc/Spring Security Test for servlet or WebTestClient/security test support for reactive. GraphQlTester running directly against the GraphQL service may not pass through the full HTTP security filter chain; choose the tester matching the protection layer being verified.

Cases to test:

1. User A reads a resource belonging to A successfully.
2. User A swaps the ID argument to User B's resource and is denied.
3. A user in tenant A cannot read resources of tenant B.
4. Having a general authority without resource ownership is still denied.
5. Mutations perform no side effects when authorization fails.
6. Input cannot arbitrarily modify ownerId, tenantId, or unauthorized roles.
7. Nested fields with sensitive arguments are checked against the source object and arguments.
8. Calling the same field via multiple aliases with different IDs checks each separately.
9. DataLoader/batch queries do not return cross-tenant data.
10. Subscriptions do not open unauthorized topics and stop when permissions are revoked per policy.
11. Forbidden/Not Found follows anti-enumeration policy.
12. Async/reactive resolvers retain the proper security context.

In addition to the response, verify repositories/services were not called or no data changed when requests are denied. For mutations, assert record counts and before/after state to prove no side effects occurred.

## 18. Common issues

| Anti-pattern | Risk | Fix |
| --- | --- | --- |
| Trusting client-sent id | Users read/edit others' resources | Check ownership/tenant against the principal |
| Using userId/tenantId in input as identity | Client spoofs scope | Obtain identity from the authenticated SecurityContext |
| Checking only general roles | Misses object-specific permissions | Combine RBAC with ABAC/object-level checks |
| Protecting only root queries | Nested fields can still leak data | Protect every sensitive field and corresponding service |
| Using @PostAuthorize for mutations | Side effects happen before denial | Check before side effects via @PreAuthorize/service policy |
| Binding entire entity from input | Mass assignment modifies sensitive fields | Use allowlisted input DTOs and explicit mapping |
| Caching decisions solely by field name | Permission result for another resource gets reused | Cache by principal, action, resource, and scope if truly needed |
| Batch loader skips tenant filter | Data leaks through DataLoader | Apply scope/authorization in batch queries |
| SecurityContext lost in async | Resolver runs with missing or wrong context | Use Reactor Context or appropriate context propagation |
| Testing only anonymous users | Fails to catch BOLA between two valid users | Test ID swapping and cross-tenant access |
| Returning different errors exposing resources | Resource enumeration | Apply a uniform NOT_FOUND/FORBIDDEN policy |

## 19. Design principles

Treat every GraphQL argument as client-controlled data. Use @Argument or @Arguments to bind values, but base permission decisions on the authenticated principal, action, resource, and tenant from trusted sources. Combine general authorities with object-level policies; place critical rules at the application service/domain so all entry points obey them.

Check permissions before side effects, scope queries by tenant/resource, and allow input DTOs to contain only fields clients are genuinely allowed to modify. Protect nested fields, evaluate each alias/argument independently, and maintain authorization across DataLoader/async/reactive flows. Use GraphQlTester to verify valid access, IDOR/BOLA, cross-tenant isolation, mutation side effects, and error disclosure.

In Spring for GraphQL, arguments tell the server what the client wants to do and which resource it wants to access. Only an authorization service backed by server-verified identity and policy can decide whether that request is permitted.
