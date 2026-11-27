# @PreAuthorize on Repositories and CRUD Methods

## Objective

Spring Data REST automatically exposes repositories as REST resources. When an application enables Spring Security, `@PreAuthorize` can be used to check permissions right at repository methods before Spring Data REST performs a read or write operation.

You can place `@PreAuthorize` at the repository level to apply a default policy for the entire repository, then override the policy on individual methods when a specific operation requires different permissions. This approach protects calls going through the REST exporter as well as repository calls from services or other components in the application.

Three points must be clearly understood:

- Method security must be enabled with `@EnableMethodSecurity`.
- Method-level annotations override repository-level annotations; the two expressions are not automatically combined.
- To protect all CRUD operations, you must inspect all overloads and inherited methods provided by the repository, especially delete variants.

## 1. Method security in the Spring Data REST flow

Suppose the application exports an Order repository:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, UUID> {
}
~~~

REST requests are normally routed to the corresponding repository operations:

| HTTP request | Commonly used repository operation |
|---|---|
| `GET /orders` | `findAll(...)` |
| `GET /orders/{id}` | `findById(id)` |
| `POST /orders` | `save(entity)` |
| `PUT /orders/{id}` | `save(entity)` |
| `PATCH /orders/{id}` | `save(entity)` |
| `DELETE /orders/{id}` | `deleteById(id)` or the corresponding delete operation |

High-level processing flow:

~~~text
HTTP request
     |
     v
Spring Security filter chain
     |
     v
Spring Data REST handler
     |
     v
Repository proxy
     |
     v
Method Security interceptor (@PreAuthorize)
     |
     +---- denied ----> AccessDeniedException
     |
     v
Repository method executes
     |
     v
HTTP response
~~~

Request-level authorization in the filter chain can block requests by URL and HTTP method. Method security checks permissions upon invoking the repository method. These two layers complement each other: a request may pass the URL rule and still be denied when invoking the repository method.

Because method security sits on the repository proxy, rules also apply when internal application services call the same repository method directly. This is helpful when the same repository is used by a REST API, scheduled jobs, or other services.

## 2. Enabling method security

With modern Spring Security, enable pre/post method authorization with `@EnableMethodSecurity`:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

`prePostEnabled` defaults to `true`, so `@EnableMethodSecurity` alone enables `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter`.

If the project uses an older Spring Security version, the configuration may use:

~~~java
@Configuration
@EnableGlobalMethodSecurity(prePostEnabled = true)
public class LegacyMethodSecurityConfiguration {
}
~~~

Do not enable both annotations. Use the configuration matching your project's Spring Security version.

A modern web configuration can declare its own filter chain:

~~~java
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

This is an illustrative example for HTTP Basic. Real-world applications may use form login, OAuth2 Resource Server, sessions, or other authentication mechanisms. The `anyRequest().authenticated()` rule provides a default layer of protection for requests; method security continues to enforce fine-grained repository permissions.

Do not simply enable method security and leave unannotated endpoints freely accessible. Spring Security notes that methods without method-security annotations are not automatically protected. Always have a default request-level policy in `HttpSecurity`.

## 3. Repository-level @PreAuthorize

Place the annotation on the repository interface to require a common permission for every method invoked through the repository proxy:

~~~java
@RepositoryRestResource(path = "orders")
@PreAuthorize("hasRole('USER')")
public interface OrderRepository
        extends JpaRepository<Order, UUID> {
}
~~~

With this configuration, the principal needs the authority corresponding to the USER role before calling repository methods such as `findById`, `findAll`, `save`, or `delete`.

`hasRole('USER')` checks the `ROLE_USER` authority under Spring Security's default role prefix. If you want to check an exact authority, you can use:

~~~java
@PreAuthorize("hasAuthority('order:read')")
Optional<Order> findById(UUID id);
~~~

Roles work well for broad permission groups; authorities such as `order:read`, `order:create`, or `order:delete` can express finer-grained business permissions.

Official Spring Data REST documentation illustrates placing `@PreAuthorize` at the repository level to protect the entire repository. This serves as the default policy for methods except those with their own annotations.

## 4. Overriding permissions on individual CRUD methods

When a method needs a separate policy, override the method from `CrudRepository`/`JpaRepository` and place `@PreAuthorize` directly on the method:

~~~java
@RepositoryRestResource(path = "orders")
@PreAuthorize("hasRole('USER')")
public interface OrderRepository
        extends JpaRepository<Order, UUID> {

    @Override
    @PreAuthorize("hasRole('ADMIN')")
    Optional<Order> findById(UUID id);

    @Override
    @PreAuthorize("hasRole('ADMIN')")
    void deleteById(UUID id);

    @Override
    @PreAuthorize("hasRole('ADMIN')")
    void delete(Order order);

    @Override
    @PreAuthorize("hasRole('ADMIN')")
    void deleteAll(Iterable<? extends Order> orders);

    @Override
    @PreAuthorize("hasRole('ADMIN')")
    void deleteAll();
}
~~~

Meaning:

- The repository-level policy requires role USER for methods without their own annotations.
- `findById` and the delete methods require role ADMIN.
- Methods with their own annotations use the method-level expression instead of the repository-level expression.

**The two annotation levels do not automatically combine.** If the repository requires USER but a method has `@PreAuthorize("hasRole('ADMIN')")`, that method only evaluates the ADMIN expression. If business rules require the caller to have both roles, write the combined condition explicitly:

~~~java
@PreAuthorize("hasRole('USER') and hasRole('ADMIN')")
void deleteById(UUID id);
~~~

Do not assume that method-level ADMIN automatically inherits and adds the repository-level USER condition. This is an important rule when organizing permissions across multiple levels.

## 5. Thoroughly protecting delete methods

A common mistake is overriding only `deleteById` and assuming all delete operations are protected. `CrudRepository` provides multiple delete variants:

- `deleteById(ID id)`
- `delete(T entity)`
- `deleteAll(Iterable<? extends T> entities)`
- `deleteAll()`

Spring Data REST documentation emphasizes overriding all of these delete methods if you want a separate policy for delete operations. If you only protect one overload, calls through another overload may still use the repository-level policy or another unintended policy.

Example separating read and delete permissions:

~~~java
@RepositoryRestResource(path = "orders")
@PreAuthorize("hasAuthority('order:read')")
public interface OrderRepository
        extends JpaRepository<Order, UUID> {

    @Override
    @PreAuthorize("hasAuthority('order:delete')")
    void deleteById(UUID id);

    @Override
    @PreAuthorize("hasAuthority('order:delete')")
    void delete(Order order);

    @Override
    @PreAuthorize("hasAuthority('order:delete')")
    void deleteAll(Iterable<? extends Order> orders);

    @Override
    @PreAuthorize("hasAuthority('order:delete')")
    void deleteAll();
}
~~~

Check the actual CRUD interfaces of the Spring Data version in use. If an interface has additional write methods or overloads, apply the corresponding policy to those methods as well. Also review custom repository methods capable of mutating data.

## 6. Protecting create and update operations

The main repository write methods include:

- `save(S entity)`
- `saveAll(Iterable<S> entities)`

You can assign separate permissions to them:

~~~java
@RepositoryRestResource(path = "orders")
@PreAuthorize("hasAuthority('order:read')")
public interface OrderRepository
        extends JpaRepository<Order, UUID> {

    @Override
    @PreAuthorize("hasAuthority('order:write')")
    <S extends Order> S save(S entity);

    @Override
    @PreAuthorize("hasAuthority('order:write')")
    <S extends Order> List<S> saveAll(Iterable<S> entities);
}
~~~

Note that Spring Data REST commonly uses the same repository save operation for POST creations and PUT/PATCH item updates. Therefore, a `@PreAuthorize` on `save` applies to the save call regardless of whether the request originated as POST, PUT, or PATCH.

If policy requires different roles for POST and PUT/PATCH, annotating `save` alone is not enough to distinguish them. You can use request-level authorization by HTTP method/path, or create a custom controller/service with separate business methods and put method security on each of those methods.

Example distinguishing at the request layer:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.POST, "/orders").hasAuthority("order:create")
    .requestMatchers(HttpMethod.PUT, "/orders/**").hasAuthority("order:update")
    .requestMatchers(HttpMethod.PATCH, "/orders/**").hasAuthority("order:update")
    .anyRequest().authenticated()
)
~~~

Both the request-level rule and the method-level rule must be satisfied. If repository `save` also requires `order:write`, the principal must hold the corresponding permissions at both layers or the application must organize an appropriate authority/role hierarchy.

## 7. Protecting queries based on user permissions

`@PreAuthorize` does more than check roles. SpEL can use the principal, method parameters, and business beans to decide permissions.

Example allowing a user to read an Order only if they are the owner or have administrative permission:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<Order, UUID> {

    @Override
    @PreAuthorize("@orderAuthorization.canRead(authentication, #id)")
    Optional<Order> findById(@Param("id") UUID id);
}
~~~

Permission-checking bean:

~~~java
@Component("orderAuthorization")
public class OrderAuthorization {

    private final OrderPermissionService permissionService;

    public OrderAuthorization(OrderPermissionService permissionService) {
        this.permissionService = permissionService;
    }

    public boolean canRead(Authentication authentication, UUID orderId) {
        return permissionService.canRead(authentication, orderId);
    }
}
~~~

`@Param("id")` provides the parameter name for the SpEL expression. Spring Security can also discover parameter names from `@P` or when compiled with the `-parameters` option. For repository interfaces, declaring parameter names explicitly keeps expressions readable and stable.

Do not embed complex queries or numerous business rules inside long SpEL strings. Move that logic into a dedicated authorization bean so it can be unit tested independently.

## 8. Distinguishing @PreAuthorize and @PostAuthorize

`@PreAuthorize` checks permissions before the method executes. This is the right choice for write methods because it can reject requests before modifying the database.

`@PostAuthorize` checks the result after the method runs. Example:

~~~java
@PostAuthorize("returnObject.orElse(null)?.owner == authentication.name")
Optional<Order> findById(UUID id);
~~~

This can be useful when permissions must be evaluated against the entity just read. However, do not use `@PostAuthorize` to protect write methods such as `save` or `delete`: data may already be modified before the post-check denies the result.

For write operations, check permissions before execution using `@PreAuthorize`. If permission depends on the existing entity's owner, call an authorization bean from SpEL to load/verify ownership before allowing the operation.

## 9. Combining method security with request-level security

Method security and URL security protect different points:

| Protection layer | Checks | Example |
|---|---|---|
| Request-level | URL, HTTP method, authentication state | Only ADMIN can call DELETE /orders/** |
| Repository-level | Every repository method call | User needs order:read to call the repository |
| Method-level | A specific CRUD operation | Only order:delete can call deleteById |
| Object-level | Permissions on a specific entity | Only owner or ADMIN can read Order 42 |

Example request-level rule:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.DELETE, "/orders/**")
        .hasAuthority("order:delete")
    .requestMatchers("/orders/**")
        .authenticated()
    .anyRequest().authenticated()
)
~~~

If only request-level security is used, internal code calling the repository directly may not go through the HTTP filter chain. Method security on the repository protects those calls as well.

If only method security is used, other endpoints that do not call the repository or unannotated methods still need a request-level policy. Use both layers according to the application's responsibility boundaries.

## 10. Testing access permissions with MockMvc

Test both permitted and denied users. Spring Security Test supports `@WithMockUser` to create an Authentication in tests.

Example:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderRepositorySecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(roles = "USER")
    void userCanReadOrders() throws Exception {
        mvc.perform(get("/orders")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotDeleteOrder() throws Exception {
        mvc.perform(delete("/orders/00000000-0000-0000-0000-000000000001"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanDeleteOrder() throws Exception {
        mvc.perform(delete("/orders/00000000-0000-0000-0000-000000000001"))
            .andExpect(status().isNoContent());
    }

    @Test
    void anonymousUserCannotReadOrders() throws Exception {
        mvc.perform(get("/orders")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isUnauthorized());
    }
}
~~~

This is an integration test skeleton; create fixtures with matching IDs and adjust success status codes according to your application's Spring Data REST configuration. If using HTTP Basic, form login, or bearer tokens, configure test requests accordingly. With `@WithMockUser(roles = "USER")`, Spring Security creates the `ROLE_USER` authority.

Beyond MockMvc, test the repository proxy directly with `@WithMockUser` or an appropriate `SecurityContext` to confirm method security still applies when a service invokes the repository without going through REST.

Scenarios to include:

- Anonymous callers blocked at the request layer.
- USER can read resources per policy.
- USER cannot invoke delete methods reserved for ADMIN.
- ADMIN can invoke allowed delete methods.
- Other delete overloads are also blocked properly.
- Method-level annotations override repository policy as expected.
- Custom finders and custom write methods also have clear policies.
- Verify data remains unchanged after denied requests.

## 11. Common pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| @PreAuthorize has no effect | Method security is not enabled | Add @EnableMethodSecurity or appropriate legacy configuration |
| REST request blocked even though URL rule allows it | Repository method has a separate unsatisfied policy | Check repository-level and method-level annotations |
| Method-level ADMIN does not require USER | Method-level annotation overrides repository-level | Combine both conditions in the same SpEL expression if needed |
| Only deleteById is protected | Other delete overloads were not overridden | Protect all delete methods of CrudRepository |
| POST and PUT do not have separate permissions | Both go through save | Distinguish via request matchers or custom service methods |
| Repository method called from service is not blocked | Method security not enabled or call bypasses proxy | Check proxy and method security configuration |
| User has role but still gets 403 | Role/authority name does not match prefix | Check ROLE_ and use hasRole/hasAuthority consistently |
| SpEL cannot find parameter | Parameter names are not discovered | Use @Param, @P, or compile with -parameters |
| Data is written before being denied | Used @PostAuthorize on a write method | Use @PreAuthorize before execution |
| Other endpoints remain accessible | Method is unannotated and request layer is too broad | Add a catch-all authorization rule in HttpSecurity |

## 12. Checklist for implementing @PreAuthorize

- Enable method security with `@EnableMethodSecurity`.
- Place a default policy on the repository interface when all operations need the same permission.
- Override methods and place dedicated annotations when a CRUD operation requires a different permission.
- Remember that method-level annotations override repository-level annotations and do not automatically combine.
- Protect all delete overloads: deleteById, delete, deleteAll(Iterable), deleteAll().
- Identify save/saveAll methods and custom methods that can write data.
- If POST and PUT/PATCH need different permissions, use request-level method/path rules or custom services/controllers.
- Use authorization beans for ownership or per-entity permission checks.
- Prefer @PreAuthorize before write operations; be cautious with @PostAuthorize.
- Combine request-level and method-level security; include a catch-all rule for requests.
- Test allowed roles, denied roles, anonymous users, and all important overloads.
- Verify database state after denied requests.

## Conclusion

`@PreAuthorize` can be placed at the repository level to protect all repository invocations, or on individual CRUD methods to apply specific policies. Spring Data REST invokes the repository proxy when handling requests, so method security checks permissions right at data operations and also protects calls from services within the application. Method-level annotations override repository-level annotations; if both conditions are required, write them in the same expression. Enable `@EnableMethodSecurity`, override all delete overloads, clearly separate POST vs PUT/PATCH permissions when they share `save`, and test both request-level and repository-level authorization.

## References

- Spring Data REST – Security and repository method authorization: https://docs.spring.io/spring-data/rest/reference/security.html
- Spring Security – Method Security, @PreAuthorize and @PostAuthorize: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Data Commons – CrudRepository API and CRUD methods: https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html
- Spring Security Test – Method security testing: https://docs.spring.io/spring-security/reference/servlet/test/method.html
