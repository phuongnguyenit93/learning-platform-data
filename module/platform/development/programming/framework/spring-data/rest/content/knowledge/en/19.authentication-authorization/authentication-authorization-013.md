# 401 and 403 Responses and Testing Unauthorized Access

When Spring Data REST exposes repositories as a REST API, Spring Security can protect collection resources, item resources, search endpoints, and association resources. When a client calls an endpoint without meeting access requirements, the API must return an appropriate, testable response.

Two common status codes are:

- **401 Unauthorized**: the request is not validly authenticated. The client must provide or refresh credentials.
- **403 Forbidden**: the request has an authenticated identity, but the user lacks permission to perform the operation.

The name "Unauthorized" for 401 is easily misunderstood. In HTTP semantics, 401 indicates missing or unacceptable authentication credentials; 403 means the server understood the request yet refuses to authorize it. For APIs using HTTP Basic, 401 typically includes the **WWW-Authenticate** header to inform the client of the authentication scheme.

## Objective

After this lesson, you will be able to:

- Distinguish 401, 403, and related statuses such as 404.
- Understand the roles of AuthenticationEntryPoint, AccessDeniedHandler, and ExceptionTranslationFilter.
- Protect Spring Data REST endpoints with URL authorization and method security.
- Return consistent JSON for authentication and authorization errors.
- Test anonymous users, invalid credentials, users lacking authorities, and authorized users using MockMvc.
- Distinguish authorization errors from CSRF and CORS errors.
- Prevent error responses from disclosing internal information.

## 1. Distinguishing 401 and 403

| Scenario | Typical response | Meaning |
| --- | --- | --- |
| No credentials sent to an endpoint requiring login | 401 | Client is unauthenticated |
| Invalid username/password or token sent | 401 | Credentials were rejected |
| Logged in but missing required role/authority | 403 | Valid identity but not permitted |
| Logged in but operation is forbidden by policy | 403 | Authorization denied the request |
| Resource does not exist | 404 | Resource not found |
| API intentionally conceals resource existence | May use 404 | Security policy does not disclose whether the resource exists |

401 and 403 represent two distinct outcomes of endpoint protection. Do not return 401 for every error, as clients may mistakenly think re-logging in will grant access. Nor should you return 403 for unauthenticated requests when the API uses an HTTP authentication challenge.

### 1.1. Spring Data REST example

Suppose a repository is exported under path /orders:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<Order, Long> {
}
~~~

An unauthenticated client calls:

~~~http
GET /orders
Accept: application/hal+json
~~~

If the endpoint requires authentication, the server returns 401.

A logged-in user with only read permission calls:

~~~http
DELETE /orders/42
Authorization: Basic ...
~~~

If deletion requires a separate authority, the server returns 403.

If a user with delete permission requests an order 42 that does not exist, the response may be 404. Do not confuse a nonexistent resource with an existing resource the caller is forbidden to access.

### 1.2. The WWW-Authenticate header

When returning 401 under an HTTP authentication challenge, the server must inform the client of the authentication scheme via the WWW-Authenticate header.

Example with Basic authentication:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="api"
Content-Type: application/problem+json
~~~

Clients can rely on the challenge to send credentials. When writing a custom AuthenticationEntryPoint, ensure the response still includes a challenge matching the authentication scheme in use.

For Bearer tokens, the challenge typically uses the Bearer scheme and may include an error attribute per RFC 6750. Never return a Basic challenge if the API actually only accepts Bearer tokens.

## 2. Where does Spring Security handle errors?

In the Servlet security filter chain, **ExceptionTranslationFilter** converts security exceptions into appropriate HTTP responses. This filter does not decide whether a user is authorized; it translates outcomes from authentication and authorization components.

General flow:

~~~text
HTTP request
    |
    v
SecurityFilterChain
    |
    v
Authentication / Authorization
    |
    +--> AuthenticationException
    |        |
    |        v
    |   AuthenticationEntryPoint
    |        |
    |        v
    |      401 / login challenge
    |
    +--> AccessDeniedException
             |
             v
       Check Authentication
             |
             +--> Anonymous / insufficiently authenticated
             |        |
             |        v
             |   AuthenticationEntryPoint
             |        |
             |        v
             |       401
             |
             +--> Authenticated
                      |
                      v
                AccessDeniedHandler
                      |
                      v
                     403
~~~

Key rules:

- **AuthenticationEntryPoint** commences authentication when the request lacks valid authentication or needs a challenge.
- **AccessDeniedHandler** handles cases where an authenticated user is denied access.
- ExceptionTranslationFilter bridges security exceptions and HTTP responses.
- Some authentication mechanisms invoke the entry point directly on invalid credentials, such as BasicAuthenticationFilter.

Anonymous users accessing a protected resource are normally routed to AuthenticationEntryPoint. Logged-in users lacking permissions trigger AccessDeniedHandler.

## 3. Configuring authorization for Spring Data REST

Spring Data REST exposes multiple endpoint categories. Decide permissions for each resource group:

- Collection resource: /orders.
- Item resource: /orders/{id}.
- Search resource: /orders/search and underlying query methods.
- Association resources: /orders/{id}/customer, /orders/{id}/items.
- Other repository resources such as customers, products, or accounts.

Example using request authorization by HTTP method:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http) throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    HttpMethod.GET,
                    "/orders/**"
                ).hasAuthority("ORDER_READ")
                .requestMatchers(
                    HttpMethod.POST,
                    "/orders/**"
                ).hasAuthority("ORDER_CREATE")
                .requestMatchers(
                    HttpMethod.PUT,
                    "/orders/**"
                ).hasAuthority("ORDER_UPDATE")
                .requestMatchers(
                    HttpMethod.PATCH,
                    "/orders/**"
                ).hasAuthority("ORDER_UPDATE")
                .requestMatchers(
                    HttpMethod.DELETE,
                    "/orders/**"
                ).hasAuthority("ORDER_DELETE")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This example illustrates a policy for the `/orders` repository path. Adjust matchers to fit your application's actual base path and endpoints.

Notes:

- Matchers are evaluated in declaration order; specific rules must precede general rules.
- /orders/** covers items as well as sub-paths like search/associations.
- hasAuthority("ORDER_READ") matches the exact authority name.
- hasRole("ADMIN") checks the ROLE_ADMIN authority by default.
- anyRequest().authenticated() requires login for remaining requests; declare permitAll() before this rule for any public endpoints.
- Never merely hide links in HAL. Missing links do not replace server-side authorization.

If the application has a base path such as /api, matchers must use the actual path, e.g., /api/orders/**. When using multiple SecurityFilterChains, verify which chain matches the request and check chain ordering.

## 4. Protecting repository methods with method security

Spring Data REST also supports Spring Security method-level authorization on repositories. This is useful when permissions are bound to specific repository operations.

Enable method security:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Apply permissions on the repository:

~~~java
@RepositoryRestResource(path = "orders")
@PreAuthorize("hasAuthority('ORDER_READ')")
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @Override
    @PreAuthorize("hasAuthority('ORDER_READ')")
    Page<Order> findAll(Pageable pageable);

    @Override
    @PreAuthorize("hasAuthority('ORDER_DELETE')")
    void deleteById(Long id);

    @Override
    @PreAuthorize("hasAuthority('ORDER_DELETE')")
    void delete(Order order);
}
~~~

The example shows how method-level rules control individual operations. For real repositories, inventory every method and overload the REST exporter can invoke.

According to Spring Data REST documentation, repository-level and method-level security annotations **do not automatically combine**; a method-level annotation overrides the repository-level rule for that method. If you need a separate delete rule, override the corresponding delete methods and annotate each one.

Spring Data REST documentation notes that CrudRepository exposes multiple delete methods. Protecting deleteById alone does not mean all other delete paths are protected. Check signatures such as delete(entity), deleteAll(iterable), deleteAll(), and any overloads present in your interface/version.

### 4.1. Request authorization vs. method security

| Mechanism | Scope | Example |
| --- | --- | --- |
| URL/request authorization | Decides by HTTP method and path | GET /orders requires ORDER_READ |
| Repository method security | Decides when a repository method is invoked | deleteById requires ORDER_DELETE |
| Service method security | Protects business logic shared across REST, batch, or message consumers | closeAccount requires ACCOUNT_CLOSE |
| Domain rules | Verifies valid business state | Only PENDING orders can be paid |

Request authorization and method security can be combined. Request authorization blocks early by path/method; method security protects operations at the repository or service layer when invoked from other entry points.

Never treat method security as a replacement for business rules. A user holding ORDER_UPDATE must still be prevented from transitioning an order into an invalid state if domain rules forbid it.

## 5. Customizing 401 responses with AuthenticationEntryPoint

For REST APIs, clients usually expect JSON instead of an HTML page or a redirect to a login form.

You can implement AuthenticationEntryPoint to produce a consistent response:

~~~java
@Component
public class ApiAuthenticationEntryPoint
        implements AuthenticationEntryPoint {

    private final ObjectMapper objectMapper;

    public ApiAuthenticationEntryPoint(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception) throws IOException {

        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setHeader(
            HttpHeaders.WWW_AUTHENTICATE,
            "Basic realm=\"api\""
        );
        response.setContentType(
            MediaType.APPLICATION_PROBLEM_JSON_VALUE
        );

        objectMapper.writeValue(
            response.getOutputStream(),
            Map.of(
                "type", "about:blank",
                "title", "Unauthorized",
                "status", 401,
                "detail", "Authentication is required."
            )
        );
    }
}
~~~

Example response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="api"
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required."
}
~~~

If the API uses Bearer tokens, change the challenge header to that scheme. Never include passwords, tokens, stack traces, or detailed internal reasons in the response.

With form login, the default AuthenticationEntryPoint may redirect users to the login page and return 302. That suits browser flows but may not fit REST clients expecting JSON 401. Configure the entry point according to client type and authentication scheme.

## 6. Customizing 403 responses with AccessDeniedHandler

AccessDeniedHandler handles requests that are authenticated yet lack permissions:

~~~java
@Component
public class ApiAccessDeniedHandler
        implements AccessDeniedHandler {

    private final ObjectMapper objectMapper;

    public ApiAccessDeniedHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException exception) throws IOException {

        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
        response.setContentType(
            MediaType.APPLICATION_PROBLEM_JSON_VALUE
        );

        objectMapper.writeValue(
            response.getOutputStream(),
            Map.of(
                "type", "about:blank",
                "title", "Forbidden",
                "status", 403,
                "detail", "You do not have permission to perform this action."
            )
        );
    }
}
~~~

Example response:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "You do not have permission to perform this action."
}
~~~

Messages should be clear enough for clients to see the operation was denied, without leaking internal permissions, policy names, data schemas, or information about other users.

### 6.1. Registering both handlers

Register both handlers in the SecurityFilterChain:

~~~java
@Configuration
@EnableWebSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(
            HttpSecurity http,
            ApiAuthenticationEntryPoint entryPoint,
            ApiAccessDeniedHandler deniedHandler) throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/orders/**")
                    .hasAuthority("ORDER_READ")
                .anyRequest().authenticated()
            )
            .httpBasic(basic ->
                basic.authenticationEntryPoint(entryPoint)
            )
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(deniedHandler)
            );

        return http.build();
    }
}
~~~

Registering the entry point on both HTTP Basic configuration and exception handling ensures consistent challenges when Basic credentials are missing or invalid and when ExceptionTranslationFilter commences authentication.

If the application uses multiple authentication mechanisms, configure appropriate handlers per filter/chain rather than applying a single Basic challenge to all requests.

## 7. Testing 401 and 403 with MockMvc

Spring Security provides Spring MVC Test integration through the spring-security-test dependency. With Spring Boot, a common setup is:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderSecurityIntegrationTest {

    @Autowired
    private MockMvc mockMvc;
}
~~~

When manually building MockMvc from a WebApplicationContext, apply springSecurity() to register security filters and test support:

~~~java
mockMvc = MockMvcBuilders
        .webAppContextSetup(context)
        .apply(springSecurity())
        .build();
~~~

### 7.1. Anonymous users receive 401

Send a request with no user or credentials attached:

~~~java
@Test
void anonymousCannotReadOrders() throws Exception {
    mockMvc.perform(
            get("/orders")
                .accept(MediaTypes.HAL_JSON)
        )
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            startsWith("Basic")
        ));
}
~~~

This test assumes the API uses HTTP Basic and the entry point returns 401 with a Basic challenge. For Bearer tokens, assert the corresponding challenge. For form login, default configuration may redirect instead of returning 401.

### 7.2. Invalid credentials receive 401

To test the authentication manager actually validating username/password, send invalid Basic credentials:

~~~java
@Test
void invalidBasicCredentialsAreRejected() throws Exception {
    mockMvc.perform(
            get("/orders")
                .with(httpBasic("alice", "wrong-password"))
        )
        .andExpect(status().isUnauthorized());
}
~~~

This tests the real authentication flow. It differs from @WithMockUser, which creates a mock Authentication in SecurityContext without validating passwords.

### 7.3. Authenticated users lacking permission receive 403

Use a user holding read authority to call an endpoint requiring delete permission:

~~~java
@Test
@WithMockUser(
    username = "alice",
    authorities = "ORDER_READ"
)
void readerCannotDeleteOrder() throws Exception {
    mockMvc.perform(
            delete("/orders/42")
                .with(csrf())
        )
        .andExpect(status().isForbidden());
}
~~~

@WithMockUser creates a test principal. Declared authorities must match configured rules. If using hasRole("ADMIN"), use roles = "ADMIN"; if using hasAuthority("ORDER_DELETE"), use authorities = "ORDER_DELETE".

### 7.4. Users with permission are allowed

Verify valid permissions so rules do not block legitimate calls:

~~~java
@Test
@WithMockUser(
    username = "admin",
    authorities = "ORDER_DELETE"
)
void userWithDeleteAuthorityCanDeleteOrder() throws Exception {
    mockMvc.perform(
            delete("/orders/42")
                .with(csrf())
        )
        .andExpect(status().isNoContent());
}
~~~

Status codes and test data depend on your application's endpoints, repositories, and response configuration. Seed test data beforehand and verify persistence state afterward if validating business outcomes too.

### 7.5. Testing custom response bodies

If using Problem Details JSON, assert status, content type, and body fields:

~~~java
@Test
@WithMockUser(authorities = "ORDER_READ")
void forbiddenResponseUsesProblemJson() throws Exception {
    mockMvc.perform(delete("/orders/42").with(csrf()))
        .andExpect(status().isForbidden())
        .andExpect(content().contentType(
            MediaType.APPLICATION_PROBLEM_JSON
        ))
        .andExpect(jsonPath("$.status").value(403))
        .andExpect(jsonPath("$.title").value("Forbidden"));
}
~~~

Testing the response contract helps clients handle errors reliably without depending on internal exception messages.

## 8. Distinguishing authorization errors from CSRF errors

A POST, PUT, PATCH, or DELETE request can receive 403 due to **CSRF protection**, even when the user is logged in and holds the required authority.

The CSRF filter validates tokens on unsafe requests when CSRF is enabled. If the token is missing or invalid, the request is rejected before endpoint authorization runs.

In MockMvc tests, include a valid token to isolate permission checks:

~~~java
mockMvc.perform(
    post("/orders")
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("ORDER_CREATE")
        ))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"customerName":"An","status":"NEW"}
        """)
);
~~~

Test CSRF separately:

~~~java
@Test
@WithMockUser(authorities = "ORDER_CREATE")
void postWithoutCsrfTokenIsForbidden() throws Exception {
    mockMvc.perform(
            post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"customerName":"An","status":"NEW"}
                """)
        )
        .andExpect(status().isForbidden());
}
~~~

When testing 403 on DELETE or POST:

- If the goal is testing roles/authorities, add .with(csrf()) when CSRF is enabled.
- If the goal is testing CSRF, intentionally omit the token or send an invalid one.
- Inspect responses/logs to identify which filter denied the request.
- Never disable CSRF globally just to make tests pass.

Only consider disabling or ignoring CSRF for an API chain when authentication does not rely on credentials automatically sent by browsers—such as Bearer tokens in the Authorization header—and the application threat model permits it. If browsers automatically send session cookies or Basic credentials, CSRF must still be addressed.

## 9. CORS and OPTIONS preflight

Browsers may send an OPTIONS CORS preflight request before the actual request. If the preflight is blocked by an authentication filter, the browser may report a CORS error even though the real request was never sent.

Configure CORS on the server with allowed origins, methods, and headers. If policy requires it, OPTIONS preflight requests can be processed prior to endpoint authorization. Do not open all OPTIONS or all origins indiscriminately.

CORS does not replace authentication or authorization. It is a browser policy controlling whether JavaScript from another origin may read responses; non-browser clients can still call the API directly.

## 10. When should 404 be returned instead of 403?

Some APIs do not want to disclose that a resource exists when the caller lacks access. In such cases, the application can deliberately return 404 for both "does not exist" and "not permitted to view".

This is an information-hiding policy, not the default meaning of 403. Use it only when backed by a clear security requirement and apply it consistently across collection, item, association, and query endpoints.

If an API always returns 404 for forbidden resources, clients cannot distinguish missing resources from hidden ones. That can affect UX, retries, and operational support. Decide based on threat model and API contract.

## 11. Testing comprehensive access scenarios

An integration test suite for Spring Data REST should include at minimum:

| Test case | Principal | Request | Expected outcome |
| --- | --- | --- | --- |
| Missing credentials | Anonymous | Protected GET collection | 401 |
| Invalid credentials | Unauthenticated | Protected GET collection | 401 |
| Read permission | ORDER_READ | GET collection/item/search | 2xx if resource exists |
| Read-only permission | ORDER_READ | DELETE item | 403 |
| Delete permission | ORDER_DELETE | DELETE item | 2xx per contract if resource exists |
| Create permission without CSRF | ORDER_CREATE | POST with CSRF enabled | 403 due to CSRF |
| Create permission with valid CSRF | ORDER_CREATE | POST | 2xx per contract |
| Permitted but item missing | Matching authority | GET or DELETE nonexistent item | 404 or status per contract |
| Unauthorized association access | Missing matching authority | GET/PUT/POST/DELETE association | 401 or 403 per auth state and policy |

Beyond status codes, verify:

- WWW-Authenticate header on 401 responses.
- Error Content-Type and JSON structure.
- Absence of stack traces, passwords, tokens, or sensitive information in responses.
- HAL link discovery does not expose unauthorized data.
- Direct calls to known URLs remain enforced by the server.
- Collections, items, searches, and associations are all protected.
- Operations via other services/repositories still obey method security when sharing business logic.

## 12. Common pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| API returns 302 instead of 401 | Form login entry point redirects to the login page | Configure an entry point suited for REST clients |
| Anonymous request returns 403 | CSRF filter or another filter rejects before the authentication entry point | Check method, CSRF token, and filter chain |
| Logged-in user still gets 403 | Authority/role mismatch, wrong role prefix, or method security denial | Inspect SecurityContext, GrantedAuthority, and expressions |
| User can read yet cannot delete | DELETE rule requires a different authority | Grant the right permission or adjust policy |
| @PreAuthorize has no effect | @EnableMethodSecurity not enabled or call bypasses proxy | Enable method security and verify bean/proxy invocation |
| Repository-level rule is overridden | Method-level annotation has separate precedence | Check and declare rules on each overridden method |
| One delete method is protected yet another overload still deletes | Only one delete signature was overridden | Inventory and protect all exported delete overloads |
| 401 response lacks WWW-Authenticate | Custom AuthenticationEntryPoint omits the challenge header | Add a challenge matching the scheme or use a standard entry point |
| 403 response leaks internal policy | Body echoes raw exception message or stack trace | Return generic messages and log details server-side |
| DELETE test always returns 403 | Missing CSRF token rather than role error | Add .with(csrf()) when testing authorization |
| @WithMockUser tests pass yet production Basic still fails | Mock user bypasses authentication manager/password validation | Add real credential tests with httpBasic or matching tokens |
| HAL link is hidden yet endpoint can still be called | Only representation hid the link without configuring authorization | Protect requests in the server filter chain or method security |
| OPTIONS gets 401/403 and browser reports CORS failure | Preflight is not handled properly | Configure CORS/preflight aligned with security policy |

## 13. Implementation workflow

1. List repository paths and endpoints exposed by Spring Data REST.
2. Determine required permissions for GET, POST, PUT, PATCH, DELETE, and association operations.
3. Configure request authorization with specific matchers by HTTP method/path.
4. Enable @EnableMethodSecurity if protecting repository or service methods.
5. Inspect CRUD overloads; never assume one method override protects every call path.
6. Choose an authentication scheme and AuthenticationEntryPoint suited to API clients.
7. Configure AccessDeniedHandler to return consistent 403 responses.
8. Keep the WWW-Authenticate challenge header aligned with the scheme on 401 responses.
9. Define CSRF and CORS policies according to client type.
10. Write MockMvc integration tests for anonymous access, invalid credentials, missing authorities, valid authorities, and CSRF.
11. Verify response status, headers, JSON body, and post-operation data state.
12. Check server logs for diagnostics without exposing internal details in client responses.

## 14. Quick checklist

- [ ] Anonymous requests to authenticated endpoints return 401 per API contract.
- [ ] 401 includes a WWW-Authenticate challenge matching the scheme.
- [ ] Invalid credentials are tested separately.
- [ ] Authenticated users lacking authority receive 403.
- [ ] Users with appropriate authority can execute operations.
- [ ] Request authorization covers collection, item, search, and association resources.
- [ ] Method security is enabled if repositories/services use @PreAuthorize.
- [ ] Delete overloads and method overrides have been audited.
- [ ] CSRF tokens are included in authorization tests for POST/PUT/PATCH/DELETE when CSRF is enabled.
- [ ] CSRF failures are tested separately.
- [ ] CORS preflight is configured without over-broadening API permissions.
- [ ] Error responses contain no stack traces or credentials.
- [ ] Direct URLs are tested, not merely HAL links.
- [ ] 404 and resource-hiding policies are tested if applied by the application.

## 15. Key takeaways

- **401**: client is unauthenticated or credentials are invalid; API should challenge using the right authentication scheme.
- **403**: client is authenticated yet lacks permission to perform the operation.
- **AuthenticationEntryPoint** handles commencing/challenging authentication.
- **AccessDeniedHandler** handles denied access for authenticated users.
- **ExceptionTranslationFilter** translates security exceptions into HTTP responses.
- **Request authorization** protects paths and HTTP methods; **method security** protects repository/service operations.
- When testing POST/PUT/PATCH/DELETE with CSRF enabled, include a valid token to isolate authorization checks.
- Verify status, headers, response bodies, and data side effects.

## References

- Spring Data REST Reference — Security: https://docs.spring.io/spring-data/rest/reference/security.html
- Spring Security Reference — Exception Translation: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security Reference — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security API — AuthenticationEntryPoint: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/AuthenticationEntryPoint.html
- Spring Security API — AccessDeniedHandler: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/AccessDeniedHandler.html
- Spring Security Reference — Spring MVC Test Integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Spring Security Reference — Running a Test as a User: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Spring Security Reference — Testing with CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- RFC 9110 — HTTP Semantics, 401 and 403: https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750.html
