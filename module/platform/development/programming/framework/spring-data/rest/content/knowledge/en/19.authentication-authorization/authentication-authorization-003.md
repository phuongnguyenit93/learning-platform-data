# Enabling Method-Level Security with @EnableMethodSecurity

Spring Security can check permissions directly at the Java methods called by users. This mechanism is called method security. In a Spring Data REST application, method security helps protect services or repositories according to business rules: for example, only a user with the ORDER_APPROVE permission can confirm an order, regardless of whether that method is invoked from a REST endpoint, another controller, or an internal component.

To enable this mechanism in modern Spring Security versions, place @EnableMethodSecurity on a configuration class. Then place annotations such as @PreAuthorize or @PostAuthorize on the methods to protect. Method-level authorization complements URL security in SecurityFilterChain; the two layers address different scopes.

## 1. What is method security?

URL security checks requests based on HTTP method and path. For example, GET /api/orders/** may require the ORDER_READ permission, while POST /api/orders/** requires ORDER_CREATE.

Method security checks permissions at the point a Java method is invoked. For example, a service may allow only users with ORDER_APPROVE to call confirm():

~~~java
@Service
public class OrderService {

    @PreAuthorize("hasAuthority('ORDER_APPROVE')")
    public void confirm(Long orderId) {
        // Execute order confirmation rules.
    }
}
~~~

If a user without the ORDER_APPROVE authority invokes the method through a Spring proxy, Spring Security rejects the call before the method body executes.

This is especially useful when the same service is called from multiple places. Permission rules live on the business method instead of being duplicated across every controller or endpoint.

## 2. Enabling method security with @EnableMethodSecurity

Create a Spring configuration class:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

In Spring Security 6, @EnableMethodSecurity enables pre/post annotations by default. Therefore, annotations such as @PreAuthorize, @PostAuthorize, @PreFilter, and @PostFilter can be used once this configuration is loaded into the application context.

Important options:

~~~java
@Configuration
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
public class MethodSecurityConfiguration {
}
~~~

- prePostEnabled enables expression-based annotations such as @PreAuthorize and @PostAuthorize. The default value is true.
- securedEnabled enables @Secured. The default value is false.
- jsr250Enabled enables JSR-250 annotations such as @RolesAllowed. The default value is false.

Only enable the annotation styles the application actually uses to keep the configuration easy to understand. @EnableGlobalMethodSecurity is the legacy configuration; for applications using modern Spring Security, prefer @EnableMethodSecurity.

## 3. Using @PreAuthorize to check before invoking a method

@PreAuthorize evaluates a permission expression before the method is executed. If the expression evaluates to false, Spring Security throws AccessDeniedException and rejects the call.

Example checking authorities:

~~~java
@Service
public class OrderService {

    @PreAuthorize("hasAuthority('ORDER_READ')")
    public PurchaseOrder findOrder(Long id) {
        return repository.findById(id)
            .orElseThrow(() -> new EntityNotFoundException("Order not found"));
    }

    @PreAuthorize("hasAuthority('ORDER_APPROVE')")
    public void approve(Long id) {
        // Check business rules and transition order state.
    }
}
~~~

Commonly used expressions:

| Expression | Meaning |
|---|---|
| hasAuthority('ORDER_READ') | The user has the exact ORDER_READ authority. |
| hasAnyAuthority('ORDER_READ', 'ORDER_ADMIN') | Has at least one of the listed authorities. |
| hasRole('ADMIN') | Has the ADMIN role; by default checked as the ROLE_ADMIN authority. |
| hasAnyRole('ADMIN', 'AUDITOR') | Has at least one role in the list. |
| isAuthenticated() | The caller is authenticated. |
| permitAll() | Allows anyone to invoke the method. |
| denyAll() | Denies all invocations. |

hasAuthority compares the exact authority name. hasRole automatically adds the ROLE_ prefix under the default role prefix configuration. For example, hasRole('ADMIN') corresponds to the ROLE_ADMIN authority; do not pass ROLE_ADMIN into hasRole if using the default prefix.

For business permissions such as ORDER_APPROVE or CUSTOMER_EXPORT, hasAuthority is usually clearer because the permission name is checked directly.

## 4. Checking permissions against method parameters

SpEL expressions can reference method parameters. This is useful when permissions depend on a specific resource, such as allowing users to view only orders they own.

Example:

~~~java
@Service
public class OrderService {

    @PreAuthorize(
        "hasAuthority('ORDER_READ_ALL') or #ownerId == authentication.name"
    )
    public List<PurchaseOrder> findOrdersFor(String ownerId) {
        return repository.findByOwnerId(ownerId);
    }
}
~~~

In the expression:

- #ownerId references the ownerId parameter.
- authentication.name is the current principal's name.
- Users with ORDER_READ_ALL can view any owner's data; others can only query their own data.

For Spring to recognize parameter names in expressions, compile with an option that preserves parameter names such as -parameters. You can also use Spring Security's @P annotation to name a parameter explicitly when needed:

~~~java
import org.springframework.security.core.parameters.P;

@PreAuthorize("#ownerId == authentication.name")
public List<PurchaseOrder> findOrdersFor(
        @P("ownerId") String owner) {
    return repository.findByOwnerId(owner);
}
~~~

If an expression relies on a resource ID, do not blindly trust an ID passed by the client. The service should load the entity and verify ownership or tenant membership against trusted system data.

## 5. Using @PostAuthorize to check the return value

@PostAuthorize evaluates permissions after the method has run. The expression can reference returnObject, which is the object returned by the method.

For example, allowing a user to read an order only if they are the owner or have administrative permission:

~~~java
@Service
public class OrderQueryService {

    @PostAuthorize(
        "returnObject.ownerId == authentication.name or hasAuthority('ORDER_READ_ALL')"
    )
    public PurchaseOrder getById(Long id) {
        return repository.findById(id)
            .orElseThrow(() -> new EntityNotFoundException("Order not found"));
    }
}
~~~

@PostAuthorize is useful when you need to inspect properties of the loaded object, such as ownerId, tenantId, or access status.

However, the method has already executed before the expression is evaluated. Therefore, for write operations such as transferring funds, deleting data, or confirming orders, prefer @PreAuthorize to reject calls before side effects occur. Do not use @PostAuthorize as the sole guard for an operation that modifies data or calls external systems.

## 6. Using @PreFilter and @PostFilter for collections

@PreFilter filters elements of a collection parameter before the method runs. @PostFilter filters elements of a returned collection after the method runs.

@PostFilter example:

~~~java
@Service
public class OrderQueryService {

    @PostFilter(
        "filterObject.ownerId == authentication.name or hasAuthority('ORDER_READ_ALL')"
    )
    public List<PurchaseOrder> findAllVisibleOrders() {
        return repository.findAll();
    }
}
~~~

filterObject represents the element currently being evaluated. Only elements satisfying the condition remain in the returned collection.

@PreFilter example:

~~~java
@PreFilter(
    "filterObject.ownerId == authentication.name",
    filterTarget = "orders"
)
public void processOrders(List<PurchaseOrder> orders) {
    // Only process elements that pass the filter condition.
}
~~~

When a method has multiple collection parameters, filterTarget specifies which parameter to filter. If there is only one eligible collection, specifying filterTarget may not be necessary.

Filter annotations are convenient for small collections, but they can filter after all data has been loaded into memory. For large collections or paginated APIs, push authorization conditions into the query/database to avoid loading data the caller cannot view and to avoid skewing pagination totals.

## 7. Using @Secured and @RolesAllowed

In addition to expression annotations, Spring Security supports two role-based annotation styles.

**@Secured**

~~~java
@Configuration
@EnableMethodSecurity(securedEnabled = true)
public class MethodSecurityConfiguration {
}
~~~

~~~java
@Secured("ROLE_ADMIN")
public void deleteOrder(Long id) {
    repository.deleteById(id);
}
~~~

@Secured checks the listed authorities. This annotation does not support complex SpEL expressions like @PreAuthorize.

**@RolesAllowed**

~~~java
@Configuration
@EnableMethodSecurity(jsr250Enabled = true)
public class MethodSecurityConfiguration {
}
~~~

~~~java
import jakarta.annotation.security.RolesAllowed;

@RolesAllowed({"ADMIN", "ORDER_MANAGER"})
public void exportOrders() {
    // Export order data.
}
~~~

@RolesAllowed belongs to JSR-250. Role names are mapped using Spring Security's role prefix configuration; by default, roles correspond to authorities prefixed with ROLE_.

When you need to check permissions against parameters, resource owners, or combine multiple conditions, @PreAuthorize is generally more flexible than @Secured and @RolesAllowed.

## 8. Combining method security with URL security in Spring Data REST

A Spring Data REST application typically has two layers of control:

- HTTP/request authorization restricts who can call a path or HTTP method.
- Method authorization restricts who can invoke a specific business operation.

Example URL configuration:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("ORDER_READ")
            .requestMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("ORDER_CREATE")
            .anyRequest().authenticated()
        )
        .build();
    }
}
~~~

Then, the service still checks business permissions:

~~~java
@PreAuthorize("hasAuthority('ORDER_APPROVE')")
@Transactional
public void approveOrder(Long id) {
    PurchaseOrder order = repository.findById(id)
        .orElseThrow(() -> new EntityNotFoundException("Order not found"));

    order.approve();
}
~~~

The caller must pass the URL check to reach the endpoint and the method check to execute the approval operation. If another controller, scheduler, or service calls the same method through the Spring proxy, the method security rule still applies.

Do not rely solely on REST paths to protect services. A business method can be called from different entry points; placing permissions on the method keeps rules attached to the business operation.

## 9. Method security works through Spring AOP proxies

Method security uses Spring interceptors and proxies to check method invocations. Therefore, calls must go through a Spring-managed bean proxy.

The following example can bypass method security:

~~~java
@Service
public class OrderService {

    public void updateAndApprove(Long id) {
        approve(id); // self-invocation: internal call on the same instance.
    }

    @PreAuthorize("hasAuthority('ORDER_APPROVE')")
    public void approve(Long id) {
        // Change order state.
    }
}
~~~

Calling this.approve() from another method in the same instance does not pass through the proxy, so the method security interceptor may not be triggered.

The common fix is to extract the protected operation into another Spring bean and call that bean through its proxy:

~~~java
@Service
public class OrderApprovalService {

    @PreAuthorize("hasAuthority('ORDER_APPROVE')")
    public void approve(Long id) {
        // Execute approval business logic.
    }
}
~~~

Another service injects OrderApprovalService and calls approve(). Calls through the bean proxy go through the permission-checking mechanism.

Other considerations:

- Ensure the service is created and managed by the Spring container.
- Avoid manually instantiating services with new if you expect method security to apply.
- For interface-based or class-based proxies, check proxy configuration and whether methods can be intercepted.
- Do not rely on self-invocation to enforce an important permission check.
- Keep protected business methods at clear service boundaries.

## 10. Distinguishing authentication and authorization

@EnableMethodSecurity enables permission checks on methods, but it does not configure how users are authenticated.

- **Authentication:** identifies who the caller is, for example via session, HTTP Basic, OAuth2 Resource Server, or JWT.
- **Authorization:** decides whether the caller is allowed to perform an operation, such as ORDER_READ or ORDER_APPROVE.

Method security uses the current Authentication in SecurityContext to evaluate expressions. The application still needs an appropriate authentication mechanism and SecurityFilterChain.

If a request is unauthenticated, request security configuration normally requires login before any method is invoked. If the user is authenticated but lacks the required authority, method security rejects the call.

## 11. Common pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| @PreAuthorize has no effect | @EnableMethodSecurity is not enabled or the bean is not called through a proxy. | Check configuration and how the bean is injected/called. |
| @Secured does not run | securedEnabled is false. | Enable securedEnabled=true. |
| @RolesAllowed does not run | jsr250Enabled is false or the corresponding annotation dependency is missing. | Enable jsr250Enabled and verify the jakarta/javax import matches the version. |
| hasRole always returns false | Confusing roles with authorities or the ROLE_ prefix. | Use hasRole('ADMIN') for ROLE_ADMIN or hasAuthority with the exact name. |
| #parameter is not recognized | Parameter names are not preserved in bytecode. | Compile with -parameters or use @P. |
| Internal call is not blocked | Self-invocation does not go through the proxy. | Extract the method to another bean and call through the proxy. |
| @PostFilter slows down the API | The entire collection is loaded before filtering. | Move conditions into the repository query/database. |
| Write operation already ran before being denied | Used @PostAuthorize for an operation with side effects. | Use @PreAuthorize to check before execution. |

When receiving AccessDeniedException, distinguish errors from URL authorization versus method authorization. You can enable appropriate logging in development to identify which interceptor or expression rejected the call; avoid writing tokens or sensitive data to logs.

## 12. Workflow for verifying method security

For the approveOrder method:

1. Enable @EnableMethodSecurity in the application context.
2. Verify unauthenticated users cannot access the API per request security configuration.
3. Call the method as a user with ORDER_READ but without ORDER_APPROVE; verify the operation is denied.
4. Call as a user with ORDER_APPROVE; verify the business logic executes.
5. Call the same service from another controller or bean to verify calls go through the proxy.
6. Test internal call paths within the same class to spot self-invocation cases.
7. If using @PostAuthorize, verify returnObject is checked after the method returns.
8. If using filter annotations, test on small collections and evaluate pushing filter conditions down to the database.
9. Verify both URL authorization and method authorization to know which layer protects each operation.

@EnableMethodSecurity enables permission checking at method boundaries. Use @PreAuthorize to protect before execution, @PostAuthorize to inspect returned results, and filter annotations when filtering collections. Place permission rules near business services, ensure calls pass through Spring proxies, and combine with URL security to thoroughly protect Spring Data REST endpoints.
