# Method Rules Override Repository-Level Security Rules

Spring Data REST exports repositories as REST APIs. Repository operations can be protected with Spring Security method security. A rule placed at the repository interface level acts as the default for its methods; when a method declares its own rule, the method-level rule takes precedence for that specific method.

This mechanism lets you apply a shared policy to the repository while restricting or broadening permissions for specific operations such as reading, searching, saving, or deleting. It is important to understand that a method-level rule **replaces** the same kind of repository-level rule for that method; they are not automatically combined with AND.

## 1. Enabling method security

Spring Security method security must be explicitly enabled in the application configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {
}
~~~

With Spring Boot, add the appropriate Spring Security dependency, for example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
~~~

**`@EnableMethodSecurity`** registers interceptors to handle annotations such as:

- **`@PreAuthorize`**: checks permissions before invoking a method.
- **`@PostAuthorize`**: checks the result after the method executes.
- **`@PreFilter`** and **`@PostFilter`**: filters collection elements or parameters according to a security expression.
- **`@Secured`** and **`@RolesAllowed`**: alternative permission declaration forms when enabled accordingly.

In modern Spring Security, **`@EnableMethodSecurity`** replaces the legacy configuration **`@EnableGlobalMethodSecurity`**. You do not need to enable both.

## 2. Setting a default rule at the repository level

**`@PreAuthorize`** can be placed directly on the repository interface. That rule applies by default to repository methods when there is no corresponding method-level rule.

For example, requiring the USER role to access repository operations:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.security.access.prepost.PreAuthorize;

@RepositoryRestResource(path = "orders")
@PreAuthorize("hasRole('USER')")
public interface OrderRepository extends JpaRepository<Order, Long> {
}
~~~

In this example:

- **`@RepositoryRestResource`** configures how the repository is exported as a REST resource.
- **`@PreAuthorize("hasRole('USER')")`** sets the default policy for methods.
- Users without the appropriate permission are blocked when calling methods through the Spring-managed repository proxy.

**`hasRole('USER')`** is shorthand for the **`ROLE_USER`** authority. If you want an exact authority match, use:

~~~java
@PreAuthorize("hasAuthority('ROLE_USER')")
~~~

Do not confuse **`@RepositoryRestResource`** with security configuration. That annotation controls resource exporting and REST mapping; **`@PreAuthorize`** is the authorization rule.

## 3. Overriding rules with method-level annotations

When a method needs a policy different from the repository default, place **`@PreAuthorize`** directly on the method.

For example: all operations default to requiring the USER role, while deleting an order is restricted to ADMIN:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.security.access.prepost.PreAuthorize;

@RepositoryRestResource(path = "orders")
@PreAuthorize("hasRole('USER')")
public interface OrderRepository extends JpaRepository<Order, Long> {

    @Override
    @PreAuthorize("hasRole('ADMIN')")
    void deleteById(Long id);
}
~~~

The rule for **`deleteById`** is **`hasRole('ADMIN')`**. Spring Security uses the method-level expression for this operation instead of the repository-level expression **`hasRole('USER')`**.

Other methods without their own annotations remain subject to the repository-level default rule.

| Method | Applied rule |
|---|---|
| **`findAll()`** | **`hasRole('USER')`** from repository |
| **`findById(id)`** | **`hasRole('USER')`** from repository |
| **`save(entity)`** | **`hasRole('USER')`** from repository |
| **`deleteById(id)`** | **`hasRole('ADMIN')`** from method |

Important takeaway: if ADMIN does not hold the USER role, ADMIN can still invoke **`deleteById`** under the method-level expression in this example. The repository-level USER rule is not automatically added to the method's ADMIN rule.

## 4. Method-level rules replace, not automatically combine

Suppose the repository has:

~~~java
@PreAuthorize("hasRole('USER')")
public interface OrderRepository extends JpaRepository<Order, Long> {

    @PreAuthorize("hasRole('ADMIN')")
    void deleteById(Long id);
}
~~~

For **`deleteById`**, the evaluated expression is **`hasRole('ADMIN')`**. It is not interpreted as:

~~~text
hasRole('USER') AND hasRole('ADMIN')
~~~

If business rules require the caller to hold both roles simultaneously, write the combined condition explicitly:

~~~java
@PreAuthorize("hasRole('USER') and hasRole('ADMIN')")
void deleteById(Long id);
~~~

If you want to allow either role:

~~~java
@PreAuthorize("hasAnyRole('USER', 'ADMIN')")
void deleteById(Long id);
~~~

Because method-level rules can replace the shared policy, carefully inspect every method that carries its own annotation. An overly broad expression can inadvertently grant access to users that the repository-level rule previously denied.

## 5. Overriding inherited CRUD methods

Repositories typically inherit methods from **`CrudRepository`**, **`ListCrudRepository`**, or **`JpaRepository`**. To apply a custom rule to an inherited method, redeclare that method in the concrete repository interface and place the annotation on the overridden declaration.

Example restricting delete and save operations:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("hasRole('USER')")
public interface OrderRepository extends JpaRepository<Order, Long> {

    @Override
    @PreAuthorize("hasRole('ADMIN')")
    void deleteById(Long id);

    @Override
    @PreAuthorize("hasRole('EDITOR') or hasRole('ADMIN')")
    <S extends Order> S save(S entity);
}
~~~

When overriding:

- Keep the exact method name and parameters from the parent interface.
- Keep a return type compatible with the inheritance contract.
- Place the annotation on the method declaration used by the repository proxy.
- Only override methods that actually need a distinct policy.

If an inherited method is not redeclared, it continues to use the repository-level default policy.

## 6. Applying dedicated rules to query methods

Method-level rules can also protect query methods exposed by Spring Data REST under **`/search`**.

For example, a repository has a general policy for USER, while an administrative query is restricted to ADMIN:

~~~java
import java.util.List;

import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RestResource;
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("hasRole('USER')")
public interface OrderRepository extends JpaRepository<Order, Long> {

    List<Order> findByStatus(String status);

    @RestResource(path = "all-customers")
    @PreAuthorize("hasRole('ADMIN')")
    List<Order> findAllByCustomerId(@Param("customerId") Long customerId);
}
~~~

Method **`findByStatus`** uses the default USER rule. Method **`findAllByCustomerId`** uses the dedicated ADMIN rule.

When a client calls the query resource, Spring Data REST invokes the repository method through its proxy. Method security checks permissions at invocation time. If the query is blocked, the client receives no results simply because the search endpoint was exported.

## 7. Using security expressions based on parameters and data

**`@PreAuthorize`** supports SpEL, so input parameters can be checked rather than only roles.

For example, allowing users to find orders within their own account scope or users with the ADMIN role:

~~~java
@PreAuthorize(
    "hasRole('ADMIN') or #accountId == authentication.principal.accountId"
)
List<Order> findByAccountId(@Param("accountId") Long accountId);
~~~

Parameter names used in SpEL must be recognized by Spring. You can use **`@P`** or **`@Param`** according to the appropriate configuration and version, and enable compiler parameter-name retention if expressions rely on Java parameter names.

For checking returned data, **`@PostAuthorize`** can inspect the object after the method completes:

~~~java
@PostAuthorize(
    "returnObject.isEmpty() or " +
    "returnObject.get().owner == authentication.name"
)
Optional<Order> findById(Long id);
~~~

Use expressions matching the actual return type. For large collections, avoid loading all data and then filtering with **`@PostFilter`**; prefer pushing permission conditions into the query or service to restrict data directly at the database.

## 8. Distinguishing method security and HTTP request security

Method security and HTTP request security operate at two different layers:

1. The HTTP security filter chain checks requests based on URL, HTTP method, authentication, and request matchers.
2. If the request passes the filter chain and calls the repository proxy, method security then checks annotations on the repository/method.

Example HTTP configuration:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/orders/**").authenticated()
            .anyRequest().permitAll()
        )
        .build();
}
~~~

If the filter chain rejects a request, a method-level **`@PreAuthorize`** rule cannot allow the request through. Conversely, a request passing a URL matcher can still be rejected by method security.

Therefore, a method-level override only replaces a repository/interface-level method rule. It does not override an independent URL rule in **`HttpSecurity`**, nor does it disable CSRF, authentication, or other filters.

## 9. Distinguishing roles, authorities, and access states

Spring Security provides several commonly used expressions:

| Expression | Meaning |
|---|---|
| **`hasRole('ADMIN')`** | Checks the default authority with prefix **`ROLE_`** |
| **`hasAuthority('order:read')`** | Checks the exact authority |
| **`hasAnyRole('USER', 'ADMIN')`** | Allows any of the listed roles |
| **`hasAnyAuthority('order:read', 'order:write')`** | Allows any of the listed authorities |
| **`isAuthenticated()`** | Requires an authenticated user |
| **`permitAll()`** | Allows everyone to invoke through method security |
| **`denyAll()`** | Denies every invocation through method security |

Example using functional permissions:

~~~java
@PreAuthorize("hasAuthority('order:read')")
List<Order> findByStatus(String status);

@PreAuthorize("hasAuthority('order:delete')")
void deleteById(Long id);
~~~

Using fine-grained authorities can be easier to manage when permissions do not map one-to-one with user roles.

## 10. Verifying method-level overrides

Verify with integration tests using different authentications and calling actual endpoints.

Example with Spring Security Test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderSecurityTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(roles = "USER")
    void userCanReadOrders() throws Exception {
        mockMvc.perform(get("/orders"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotDeleteOrder() throws Exception {
        mockMvc.perform(delete("/orders/1"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanDeleteOrder() throws Exception {
        mockMvc.perform(delete("/orders/1"))
                .andExpect(status().is2xxSuccessful());
    }
}
~~~

This test suite assumes the HTTP filter chain lets logged-in requests reach the repository and order 1 exists. Adjust expected responses to match your application's contract.

You can also test query methods by calling **`/orders/search/...`** as USER and ADMIN to verify method-level rules are enforced via search resources as well.

Common status codes:

- **`401 Unauthorized`**: request is unauthenticated or requires authentication.
- **`403 Forbidden`**: user is authenticated but lacks sufficient permissions.
- Some configurations customize how security exceptions map to responses; verify the API's actual status and body.

## 11. Common pitfalls and fixes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Annotation has no effect | **`@EnableMethodSecurity`** is not enabled | Enable method security and inspect configuration |
| Inherited method does not use custom rule | Method was not overridden in the repository interface | Redeclare the method and attach the annotation |
| ADMIN method is still blocked | HTTP filter chain or another rule rejects the request earlier | Check request matchers and filters |
| Method-level allows USER even though repository requires ADMIN | Method annotation replaces the repository-level rule | Inspect the expression and write combined conditions explicitly if needed |
| User without role can still invoke method | Call does not go through Spring proxy or annotation is not detected | Check bean, proxy, and call path |
| Internal call within the same bean is not blocked | Self-invocation bypasses AOP proxy | Invoke through a Spring-managed bean/proxy or redesign service boundaries |
| Query method leaks data | Endpoint is exported without suitable method security | Attach rules on the query method and check URL-level security too |

## 12. Policy design workflow

When securing a repository, follow this order:

1. Choose a repository default policy, such as requiring USER for all operations.
2. List methods needing different permissions, such as delete, admin, or sensitive data queries.
3. Override inherited CRUD methods if needed and place **`@PreAuthorize`** directly on those methods.
4. Write complete method-level expressions because they replace same-type repository-level expressions.
5. Inspect URL matchers in the HTTP filter chain to ensure requests can reach the target methods.
6. Test each role across collection resources, item resources, query methods, and write operations.
7. Use functional authorities or ownership checks when business rules need finer-grained control.

Repository-level policies establish consistent defaults. Method-level rules allow tuning individual operations with specific permissions. Understanding precedence and the boundary between HTTP security and method security prevents accidentally opening permissions or locking out endpoints.

Official references:

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Expression-Based Access Control](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Data REST — Security](https://docs.spring.io/spring-data/rest/reference/security.html)
