# SpEL in @PreAuthorize and security annotations

Spring Security uses the Spring Expression Language (SpEL) to write authorization conditions directly on methods through annotations such as `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter`. Expressions can check the current user's authorities, read method parameters, invoke a dedicated authorization bean, or filter data by owner.

These annotations belong to **method security**. They protect method calls passing through a Spring proxy, complementing security configuration at the HTTP layer. To use SpEL in method security, the application must enable the corresponding support and invoke methods through a Spring-managed bean.

## 1. Enabling method security

With modern Spring Security, enable method security using `@EnableMethodSecurity` on a configuration class:

    @Configuration
    @EnableMethodSecurity
    public class SecurityConfiguration {
    }

`prePostEnabled` is true by default, so `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` annotations are enabled.

If the application needs older role-based annotations, you can additionally enable:

    @Configuration
    @EnableMethodSecurity(
        securedEnabled = true,
        jsr250Enabled = true
    )
    public class SecurityConfiguration {
    }

In older Spring Security applications, configuration typically used `@EnableGlobalMethodSecurity(prePostEnabled = true)`. When upgrading, use the annotation corresponding to the project's Spring Security version.

Method security works through Spring's AOP/proxy mechanism. Simply placing an annotation on a method is not enough if the target object is not managed by Spring or the call does not go through a proxy.

## 2. Using @PreAuthorize to check before calling a method

`@PreAuthorize` evaluates the expression before the method body executes. If the expression returns false, Spring Security denies the call and the method does not run.

Example allowing administrators only:

    @PreAuthorize("hasRole('ADMIN')")
    public void deleteUser(Long userId) {
        userService.deleteById(userId);
    }

Or allowing users with a specific authority:

    @PreAuthorize("hasAuthority('invoice:read')")
    public Invoice getInvoice(Long invoiceId) {
        return invoiceRepository.findById(invoiceId)
                .orElseThrow();
    }

Multiple conditions can be combined:

    @PreAuthorize(
        "hasAuthority('invoice:read') and " +
        "@invoiceAuthorization.canRead(authentication, #invoiceId)"
    )
    public Invoice getInvoice(@P("invoiceId") Long invoiceId) {
        return invoiceRepository.findById(invoiceId)
                .orElseThrow();
    }

In this example, the caller must have the `invoice:read` authority and the `invoiceAuthorization` bean must confirm they are allowed to read the specific invoice. This is how broad permissions are combined with resource-level authorization checks.

## 3. Built-in security objects and functions in expressions

The method security expression root provides commonly used security information and functions:

| Component | Meaning |
|---|---|
| `authentication` | The current Authentication |
| `principal` | The current user's Principal |
| `hasRole('ADMIN')` | Checks for a role, with default prefix `ROLE_` |
| `hasAnyRole('ADMIN', 'SUPPORT')` | Checks for at least one role |
| `hasAuthority('invoice:read')` | Checks for an exact authority |
| `hasAnyAuthority(...)` | Checks for at least one authority |
| `isAuthenticated()` | Checks authenticated status |
| `permitAll()` / `denyAll()` | Unconditionally permits or denies |
| `hasPermission(...)` | Checks permission via PermissionEvaluator |

User information can be accessed via properties:

    authentication.name
    principal.username

Example:

    @PreAuthorize("#username == authentication.name")
    public Profile getMyProfile(String username) {
        return profileRepository.findByUsername(username);
    }

This expression only allows the caller to access a profile whose username matches the name in the current Authentication. For multi-tenant applications or complex ownership rules, also check the tenant and resource state through an authorization service.

## 4. Distinguishing role and authority

`hasRole` and `hasAuthority` match differently:

- `hasRole('ADMIN')` typically checks the `ROLE_ADMIN` authority, because the default role prefix is `ROLE_`.
- `hasAuthority('invoice:read')` matches the exact `invoice:read` authority.

Example:

    @PreAuthorize("hasRole('ADMIN') or hasAuthority('invoice:approve')")
    public void approveInvoice(Long invoiceId) {
        ...
    }

Do not pass the `ROLE_` prefix into `hasRole` if the configuration uses the default prefix; use `hasRole('ADMIN')`. If the application customizes the role prefix, role checks will follow that configuration.

Roles typically represent broad permission groups such as ADMIN or SUPPORT. Authorities typically represent specific actions such as `invoice:read`, `invoice:approve`, or `customer:export`. Choose a consistent convention so annotations do not check the wrong permission strings.

## 5. Accessing method parameters

SpEL can reference method parameters by name:

    @PreAuthorize("#ownerId == authentication.name")
    public Document findDocument(String ownerId) {
        ...
    }

For parameter names to be discovered reliably, compile Java with the `-parameters` option or declare the name using Spring Security's `@P` annotation:

    public Document findDocument(
            @P("ownerId") String ownerId) {
        ...
    }

If parameter names are unavailable, positional indices can be used:

    @PreAuthorize("#p0 == authentication.name")
    public Document findDocument(String ownerId) {
        ...
    }

The aliases `#p0` and `#a0` refer to the first parameter; `#p1` and `#a1` refer to the second parameter. Index-based access depends less on parameter name metadata, but is less readable when a method has many arguments.

For methods with multiple parameters, use clear names and test expressions under the actual build configuration. Do not assume source parameter names are always available at runtime if the compiler does not retain metadata.

## 6. Calling an authorization bean with @beanName

Method-security expressions can invoke a Spring-managed bean using the `@beanName` syntax. This is an appropriate way to keep complex domain rules in Java rather than stuffing extensive logic into SpEL strings.

Example:

    @Component("documentAuthorization")
    public class DocumentAuthorization {

        public boolean canEdit(
                Authentication authentication,
                Long documentId) {
            // Check owner, tenant, and document state.
            return ...;
        }
    }

    @PreAuthorize(
        "hasAuthority('document:write') and " +
        "@documentAuthorization.canEdit(authentication, #documentId)"
    )
    public void updateDocument(
            @P("documentId") Long documentId,
            UpdateDocumentRequest request) {
        ...
    }

The bean is resolved by Spring Security within the method-security expression context. If the application replaces the default expression handler, ensure the new configuration still supports bean resolution as required by the project.

Authorization beans should have small, clearly named methods that primarily read state to decide permissions. Do not use authorization-checking methods to write data, send notifications, or perform other side effects.

## 7. Using hasPermission for resource-level permissions

When the application has an object-level permission model, `hasPermission` can be used:

    @PreAuthorize(
        "hasPermission(#documentId, 'Document', 'READ')"
    )
    public Document getDocument(
            @P("documentId") Long documentId) {
        ...
    }

Or pass the object directly:

    @PreAuthorize("hasPermission(#document, 'WRITE')")
    public void updateDocument(Document document) {
        ...
    }

`hasPermission` delegates the decision to the PermissionEvaluator configured in Spring Security. If the application uses ACL or a custom permission model, a corresponding PermissionEvaluator must be provided. Without a suitable evaluator, do not assume the expression will automatically understand domain permissions.

For simple ownership checks, a dedicated authorization bean may be easier to read. For a general permission system, `hasPermission` helps unify permission checks across many resource types.

## 8. Using @PostAuthorize to check the return value

`@PostAuthorize` evaluates the expression after the method has executed. The `returnObject` variable references the method result:

    @PostAuthorize(
        "returnObject.owner.username == authentication.name"
    )
    public Document findDocument(Long documentId) {
        return documentRepository.findById(documentId)
                .orElseThrow();
    }

This example checks whether the current user is the owner of the returned document. If the expression is false, Spring Security denies returning the result to the caller.

Because the method body has already run before the post-condition check, do not use `@PostAuthorize` as the sole protection layer for operations with side effects such as transferring money, deleting data, or sending notifications. For operations that must prevent unauthorized execution from the start, use `@PreAuthorize`.

`@PostAuthorize` is useful when the authorization decision depends on an object that can only be determined after querying. Even so, consider querying conditionally by user or tenant so out-of-scope data is not loaded only to be denied at the end.

## 9. Using @PreFilter and @PostFilter

Both filter annotations use the `filterObject` variable to represent the element currently being checked.

**@PreFilter** filters a collection passed into the method before the method runs:

    @PreFilter(
        value = "filterObject.owner == authentication.name",
        filterTarget = "documents"
    )
    public void updateDocuments(List<Document> documents) {
        documentService.updateAll(documents);
    }

If the method has multiple collection parameters, `filterTarget` specifies which parameter to filter. If there is only one matching parameter, this attribute can be omitted.

**@PostFilter** filters the collection returned by the method:

    @PostFilter(
        "filterObject.owner == authentication.name"
    )
    public List<Document> findDocuments() {
        return documentRepository.findAll();
    }

In each predicate evaluation, `filterObject` is the current element. The result keeps only elements matching the condition.

Method-level filtering does not replace authorized data queries. For large collections, filter directly at the repository or database level by user/tenant to reduce the data loaded and processed. `@PostFilter` only filters the result after the method has run; it does not revert side effects that already occurred inside the method.

## 10. Distinguishing security annotations

| Annotation | Timing | Purpose |
|---|---|---|
| `@PreAuthorize` | Before method | Check access conditions |
| `@PostAuthorize` | After method | Check the return value |
| `@PreFilter` | Before method | Filter input collection |
| `@PostFilter` | After method | Filter result collection |
| `@Secured` | Before method | Check static list of authorities/roles |
| `@RolesAllowed` | Before method | Check JSR-250 roles |

`@Secured` and `@RolesAllowed` are not annotations that contain SpEL expressions. They use a static list of roles/authorities. To express dynamic conditions based on parameters, principal, or domain data, use the pre/post annotation group.

Example:

    @Secured("ROLE_ADMIN")
    public void rebuildIndex() {
        ...
    }

    @RolesAllowed({"ADMIN", "SUPPORT"})
    public void viewSupportDashboard() {
        ...
    }

To enable these two annotation groups, configure `@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)`.

## 11. Method security and Spring proxies

Method security is usually enforced via a Spring AOP proxy. Therefore, calls must go through the proxy of a Spring-managed bean.

An easily overlooked case is self-invocation:

    @Service
    public class InvoiceService {

        public void process(Long id) {
            approve(id); // Internal call on this
        }

        @PreAuthorize("hasAuthority('invoice:approve')")
        public void approve(Long id) {
            ...
        }
    }

The call `approve(id)` from the `process` method goes directly on the same instance, not through the external proxy. As a result, the method security interceptor may not be triggered for this internal call.

Place security boundaries on methods called through a bean proxy from outside, or separate protected operations into a dedicated Spring bean. Avoid relying on annotations on internal methods without testing the actual call path.

Also verify method visibility and the proxy type used by the application. A safe practice is to place annotations on service methods called through a Spring bean and test by retrieving the bean from the ApplicationContext rather than instantiating the object manually with `new`.

## 12. Testing method-security expressions

Test both allowed and denied cases. Spring Security Test provides annotations such as `@WithMockUser` to set up Authentication for tests:

    @Test
    @WithMockUser(authorities = "invoice:read")
    void userCanReadInvoice() {
        Invoice invoice = invoiceService.getInvoice(10L);
        assertNotNull(invoice);
    }

And the case lacking authority:

    @Test
    @WithMockUser(authorities = "invoice:write")
    void userCannotReadInvoiceWithoutReadAuthority() {
        assertThrows(
                AccessDeniedException.class,
                () -> invoiceService.getInvoice(10L)
        );
    }

Tests should call the method through an injected Spring bean so that the proxy and method-security interceptor actually operate. For expressions using parameters, verify parameter name binding on the actual build. For authorization beans or PermissionEvaluator, test owner, non-owner, wrong tenant, and nonexistent resource cases according to application policy.

## 13. Principles for designing safe expressions

- Use `@PreAuthorize` for decisions that must occur before the method body.
- Use `hasAuthority` for action-specific permissions; use `hasRole` for roles following prefix conventions.
- Use `#parameter` or `#p0` to reference arguments; configure metadata or `@P` for stable parameter names.
- Move complex domain logic into an authorization bean or PermissionEvaluator.
- Do not place side effects inside methods whose sole purpose is checking permissions.
- Do not use `@PostAuthorize` as a substitute for pre-checks on actions with side effects.
- Limit `@PostFilter` on large collections; prefer authorized queries at the repository level.
- Ensure calls go through a Spring proxy and test with a Spring-managed bean.
- Do not concatenate user data directly into dynamic SpEL strings; keep expressions in trusted code and pass data via parameters.

## 14. Key takeaways

Spring Security uses SpEL in `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` to check permissions or filter data at method boundaries. Expressions can use Authentication, principal, roles/authorities, method parameters, `returnObject`, `filterObject`, bean references, and `hasPermission`. Enable method security with `@EnableMethodSecurity`, place annotations on Spring-managed beans, and ensure calls go through a proxy. Use pre-authorization to prevent a method from running without permission; post-authorization only checks after the method has executed. Keep authorization logic clear, limit side effects, and test both allowed and denied call paths.
