# Integrating SecurityFilterChain with Spring Data REST Paths

Spring Data REST automatically exposes repositories as REST endpoints. When adding Spring Security, you need to configure a SecurityFilterChain to control access to the API root, collection, item, association, search, and metadata endpoints. Rules must match the actual base path and HTTP methods exposed by Spring Data REST.

SecurityFilterChain protects requests at the HTTP layer. It decides which requests require authentication, which authorities are required, and which requests are allowed to proceed. If the application also has services called from multiple entry points, combine this with method security to protect business operations at the service boundary.

## 1. Which paths does Spring Data REST expose?

Suppose a repository is exposed under the base path /api:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
~~~

Spring Data REST can expose paths in the following forms:

| Resource | Example path | Purpose |
|---|---|---|
| API root | /api | Discover repository resources. |
| Collection | /api/orders | Read or create the collection of orders. |
| Item | /api/orders/42 | Read, update, or delete a single order. |
| Association | /api/orders/42/customer | Read or modify the customer association. |
| Search | /api/orders/search/by-status | Invoke an exposed query method. |
| Profile | /api/profile | Read API metadata/profile. |

The exact paths depend on RepositoryRestConfiguration, @RepositoryRestResource, @RestResource, and the actual query methods. The example above uses the path orders; if the repository changes its path or the application changes its base path, the security matchers must also be updated.

Before writing matchers, determine the base path and the endpoints the application actually exposes from known configuration. Do not guess a path solely from the repository or entity name.

## 2. Where does SecurityFilterChain operate?

SecurityFilterChain is a chain of filters that processes HTTP requests before they reach a controller or Spring Data REST handler. In a typical configuration, Spring Security performs the following steps:

1. Identifies the request and selects the matching SecurityFilterChain.
2. Applies an authentication mechanism such as session, HTTP Basic, or bearer token.
3. Evaluates authorization rules in matcher order.
4. Rejects the request if the caller is unauthenticated or lacks the required authority.
5. Forwards valid requests to Spring MVC/Spring Data REST.

Request-level security configuration is suited for protecting groups of paths and HTTP methods. For example, a user with ORDER_READ can GET collections and items, while a user with ORDER_CREATE can POST to the collection.

Do not confuse an authenticated request with an authorized request. A user can log in successfully and still lack the authority required for a specific endpoint.

## 3. Basic SecurityFilterChain configuration

The following example protects the /api base path and authorizes requests by HTTP method:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.OPTIONS, "/api/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/profile").authenticated()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("ORDER_READ")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("ORDER_CREATE")
                .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("ORDER_UPDATE")
                .requestMatchers(HttpMethod.PATCH, "/api/orders/**")
                    .hasAuthority("ORDER_UPDATE")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("ORDER_DELETE")
                .requestMatchers("/api/**").denyAll()
                .anyRequest().authenticated()
            )
            .build();
    }
}
~~~

Matchers are evaluated in declaration order. Specific rules must come before general rules. If you place requestMatchers("/api/**").denyAll() first, subsequent matchers will not apply to requests under /api.

In the example, OPTIONS is permitted to support CORS preflight requests; the actual CORS configuration still needs to declare the allowed origins, methods, and headers. Do not permit all HTTP methods across the entire API just to make preflight work.

The final rule anyRequest().authenticated() requires authentication for all remaining paths. Adjust it to match the application policy and ensure administrative or internal endpoints are not inadvertently exposed.

## 4. Authorizing collections and items by HTTP method

Collections and items typically support different operations:

- GET collection: read the list.
- POST collection: create a resource.
- GET item: read a single resource.
- PUT item: replace or update a resource according to the endpoint's semantics.
- PATCH item: partial update.
- DELETE item: delete a resource.

You can configure matchers by method and path:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders", "/api/orders/**")
        .hasAuthority("ORDER_READ")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("ORDER_CREATE")
    .requestMatchers(HttpMethod.PUT, "/api/orders/**")
        .hasAuthority("ORDER_UPDATE")
    .requestMatchers(HttpMethod.PATCH, "/api/orders/**")
        .hasAuthority("ORDER_UPDATE")
    .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
        .hasAuthority("ORDER_DELETE")
    .anyRequest().authenticated()
)
~~~

Verify path matchers against your Spring Security version and how the application declares request matchers. Patterns may match more sub-endpoints than expected. If you only want to allow GET on collections and items, specify the paths explicitly and test association/search endpoints as well.

A broad GET rule for /api/orders/** also covers sub-paths such as associations or searches. If an association has its own permission, place a specific matcher for it before the broad matcher, or design matchers per endpoint group.

## 5. Protecting association endpoints

Spring Data REST can expose association resources to read or modify relationships between entities. For example:

~~~text
GET    /api/orders/42/customer
PUT    /api/orders/42/customer
DELETE /api/orders/42/customer
~~~

Association operations can mutate business data even though the URL is not a typical collection or item CRUD path. Therefore, do not overlook them when designing authorization.

Example requiring dedicated authorities to modify the customer association:

~~~java
.requestMatchers(
    HttpMethod.PUT,
    "/api/orders/*/customer"
).hasAuthority("ORDER_ASSIGN_CUSTOMER")
.requestMatchers(
    HttpMethod.DELETE,
    "/api/orders/*/customer"
).hasAuthority("ORDER_REMOVE_CUSTOMER")
~~~

The patterns above only illustrate known association paths. If an association has multiple levels or a different name, use the actual exposed path. Also consider collection associations, such as /api/orders/42/items, because POST/DELETE there can add or remove related elements.

If a general matcher allows all POST or PUT requests under /api/orders/**, it may unintentionally allow modifying associations with standard CRUD authorities. Place specific association rules before general rules.

## 6. Protecting search endpoints

Query methods can be exposed under /search, for example:

~~~text
GET /api/orders/search/by-status?status=CONFIRMED
~~~

Search endpoints are usually read-only, but the queried data may be sensitive. Assign appropriate permissions:

~~~java
.requestMatchers(
    HttpMethod.GET,
    "/api/orders/search/**"
).hasAuthority("ORDER_READ")
~~~

If there is a search for sensitive data or administrative functions, assign a separate authority. For example, searching all customers might require CUSTOMER_READ_ALL instead of permission to read a single resource owned by the user.

Place specific search matchers before the general GET matcher if the search policy differs from item read permissions. Check both the actual query method name and whether the method is exposed via @RestResource.

## 7. API root, profile, and metadata

The API root helps clients discover repository resources. Profile or metadata endpoints can also reveal domain structure, property names, or links exposed by the application.

You can allow authenticated users to read the API root:

~~~java
.requestMatchers(HttpMethod.GET, "/api").authenticated()
.requestMatchers(HttpMethod.GET, "/api/profile").authenticated()
~~~

If metadata is considered public, you can use permitAll for those exact GET paths. Do not permit all of /api/** just so clients can read the API root.

Profile and API root do not necessarily contain business data, yet they still expose the API surface. Choose a policy that fits the deployment model and security requirements.

## 8. Using authorities and roles consistently

Spring Security supports checking both authorities and roles. hasAuthority("ORDER_READ") compares the exact authority name. hasRole("ADMIN") typically checks the ROLE_ADMIN authority using the default role prefix.

Example:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("ORDER_READ")
.requestMatchers("/api/admin/**")
    .hasRole("ADMIN")
~~~

Prefer authorities for specific operational permissions such as ORDER_READ, ORDER_APPROVE, or ORDER_EXPORT. Roles typically represent user groups such as ADMIN, SUPPORT, or AUDITOR.

Do not mix the two naming conventions. If the permission assignment uses ROLE_ORDER_READ, then hasAuthority("ORDER_READ") will not match. Standardize how GrantedAuthority values are issued in UserDetails, the JWT converter, or whichever authentication mechanism is in use.

## 9. Separating multiple SecurityFilterChains when needed

An application may have multiple request types with different protection mechanisms, such as a stateless API using bearer tokens and a web UI using sessions. In that case, you can define multiple SecurityFilterChain beans and use securityMatcher to select the chain:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("ORDER_READ")
            .anyRequest().authenticated()
        )
        .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

securityMatcher selects all requests belonging to the chain; requestMatchers inside the chain decide authorization for each selected request.

The API chain must be ordered appropriately and have a clear matcher. Requests that do not match the first chain are evaluated by the next chain. If no chain matches, requests may not be protected according to the intended policy; therefore, ensure there is a default chain covering remaining requests.

Do not create multiple chains just to split a few matchers if a single chain is already clear enough. Multiple chains increase debugging complexity because you must determine which chain is handling a request.

## 10. Authentication, sessions, and bearer tokens

SecurityFilterChain configures authorization, but it also integrates with the authentication mechanism.

For session-based APIs, the application can use form login or an appropriate login mechanism. For stateless APIs, you can configure an OAuth2 Resource Server to validate JWTs:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("ORDER_READ")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
        .build();
}
~~~

JWTs must be converted into an Authentication and GrantedAuthority instances following the convention used by the matchers. If a token contains a scope such as orders.read, Spring Resource Server typically maps scopes to authorities prefixed with SCOPE_; the matcher can then use hasAuthority("SCOPE_orders.read") or configure a custom converter.

Do not assume a role claim in a JWT automatically becomes ROLE_ADMIN. Configure a JwtAuthenticationConverter if the token uses a custom claim or prefix.

With session cookies, consider CSRF for state-changing requests. With stateless bearer-token APIs, how CSRF is configured depends on whether credentials are automatically sent by the browser. Only disable CSRF when the authentication model and application risk profile allow it; do not copy a stateless configuration to an API using session cookies.

## 11. CORS and preflight requests

When a JavaScript client runs from a different origin, the browser may send an OPTIONS preflight request before the actual request. Configure CORS in Spring Security:

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.com"));
    config.setAllowedMethods(List.of(
        "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"
    ));
    config.setAllowedHeaders(List.of(
        "Authorization", "Content-Type", "Accept", "If-Match"
    ));
    config.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
~~~

Enable CORS in the chain:

~~~java
http.cors(Customizer.withDefaults());
~~~

If using credentials, declare explicit origins; do not use wildcard origins with credentials. CORS only controls whether the browser allows JavaScript to read cross-origin responses. It does not replace authentication or authorization.

Do not allow OPTIONS by opening up all requests. Let CORS handle preflight requests and restrict allowed origins, methods, and headers to actual requirements.

## 12. Combining request authorization with method security

A request may pass through SecurityFilterChain and then call a business service. HTTP-layer permissions protect paths; method security protects specific operations at the service layer.

Example:

~~~java
@Service
public class OrderService {

    @PreAuthorize("hasAuthority('ORDER_APPROVE')")
    @Transactional
    public void approve(Long orderId) {
        PurchaseOrder order = repository.findById(orderId)
            .orElseThrow(() -> new EntityNotFoundException("Order not found"));

        order.approve();
    }
}
~~~

SecurityFilterChain can allow users with ORDER_READ to access GET endpoints. However, only users with ORDER_APPROVE can invoke the approve method through the Spring proxy.

This is useful when the same service is called from another controller, a scheduler, or a message consumer. However, method security works via Spring AOP proxies; self-invocation within the same bean can bypass the interceptor. Call through the bean proxy or extract the protected operation into a separate service.

Do not place all permission rules solely in controllers because another entry point might invoke the service without going through that controller.

## 13. Matcher rules must reflect per-operation permissions

One way to organize rules is to group endpoints by permission:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/search/**")
        .hasAuthority("ORDER_READ")
    .requestMatchers(HttpMethod.GET, "/api/orders", "/api/orders/**")
        .hasAuthority("ORDER_READ")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("ORDER_CREATE")
    .requestMatchers(HttpMethod.PUT, "/api/orders/**")
        .hasAuthority("ORDER_UPDATE")
    .requestMatchers(HttpMethod.PATCH, "/api/orders/**")
        .hasAuthority("ORDER_UPDATE")
    .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
        .hasAuthority("ORDER_DELETE")
    .requestMatchers("/api/**").denyAll()
    .anyRequest().authenticated()
)
~~~

This is a baseline example; the application must adjust it for associations, action endpoints, profiles, searches, and other repositories. If an association POST/PUT requires a separate permission, place its specific matcher before the general matcher.

The denyAll rule for the remainder of the API provides default-deny behavior: newly exposed endpoints are denied until permissions are explicitly assigned. This helps when new repositories or query methods are added and inadvertently expand the API surface.

When an application has many repositories, group matchers by domain or create helper methods to keep the configuration readable. Avoid overly broad patterns that cause permissions for one resource to inadvertently apply to another.

## 14. Testing SecurityFilterChain with MockMvc

Test both allowed and denied requests. Example:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderSecurityIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(authorities = "ORDER_READ")
    void readerCanGetOrders() throws Exception {
        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "ORDER_READ")
    void readerCannotCreateOrder() throws Exception {
        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"status\":\"DRAFT\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousUserCannotReadOrders() throws Exception {
        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

The status for anonymous requests depends on the authentication entry point. With HTTP Basic or bearer APIs, you typically get 401; with form login, requests may be redirected to the login page. Write assertions matching the application's actual authentication mechanism.

Tests should cover at least:

- Anonymous users cannot access endpoints requiring authentication.
- Users with ORDER_READ can read collections and items.
- Users with only ORDER_READ cannot POST, PUT, PATCH, or DELETE.
- Users with the corresponding authority can perform allowed operations.
- Association and search endpoints enforce their own permissions.
- API root and profile follow the chosen policy.
- OPTIONS preflight works with allowed origins and headers.
- New or unmatched endpoints are denied by denyAll if default-deny is used.

When testing auto-exposed repository endpoints, use the exact configured base path and relation names. Do not test only custom controllers because Spring Data REST handlers may expose different paths.

## 15. Common pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| GET collection returns 403 | Authority mismatch or wrong matcher path. | Check GrantedAuthority, base path, and HTTP method. |
| POST is unexpectedly allowed | POST matcher is too broad or matcher order is wrong. | Place specific matchers before general patterns. |
| Association can still be modified | General CRUD matcher already covers the association. | Add specific association matchers and dedicated permissions. |
| Search endpoint is denied | Missing matcher for /search/** or mismatched permission. | Add a search matcher matching the data policy. |
| API root is inaccessible | Matchers were only configured for repository paths. | Define the policy and add a GET /api matcher. |
| CORS preflight returns 401/403 | OPTIONS or CORS is not configured properly. | Enable http.cors and declare appropriate origins/methods/headers. |
| Valid JWT still returns 403 | Claims are not mapped to the authority required by matchers. | Inspect JwtAuthenticationConverter and prefixes. |
| Service rules do not run | Method security is not enabled or self-invocation bypasses the proxy. | Enable @EnableMethodSecurity and invoke through a Spring bean proxy. |
| New endpoints are automatically open | Broad matcher permits the entire API. | Use default-deny and add explicit permissions. |

## 16. Implementation workflow

When integrating SecurityFilterChain with Spring Data REST:

1. Identify the Spring Data REST base path and exposed repository paths.
2. List collection, item, association, search, API root, and profile endpoints to protect.
3. Define permissions by HTTP method and business requirements, including separate permissions for associations or sensitive data.
4. Configure specific matchers before general matchers.
5. Choose an appropriate authentication mechanism: session, HTTP Basic in suitable environments, or bearer token/JWT.
6. Configure CSRF according to the actual credential model.
7. Configure CORS for the origins, methods, and headers actually needed.
8. Use default-deny for ungranted API paths if required by policy.
9. Enable method security for critical service operations called from multiple entry points.
10. Write MockMvc integration tests for allowed requests, denied requests, associations, searches, API root, and preflight.
11. Re-verify whenever adding repositories, query methods, or changing the base path, as the endpoint surface may change.

SecurityFilterChain controls requests to Spring Data REST paths by HTTP method and authority. Identify the exact base path, protect collections, items, associations, searches, and metadata, and order matchers from specific to general. Combining request authorization with method security, appropriate CORS/CSRF, and integration tests keeps API access consistent as repositories or endpoints evolve.
