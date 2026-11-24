# 401 or 403 Due to Security Configuration and Request Data

When a Spring endpoint returns **401 Unauthorized** or **403 Forbidden**, the error usually originates in Spring Security before the controller is invoked, from authorization rules in method security, or from request data that changes the access decision. To diagnose accurately, determine at which layer the request stopped, how the caller was authenticated, which authorities are present, and whether the request carries required security metadata such as a CSRF token.

These two status codes have distinct meanings. 401 generally indicates the request lacks valid authentication and requires an authentication mechanism; 403 generally indicates the request was identified yet is not permitted to perform the action. However, the application's `AuthenticationEntryPoint`, `AccessDeniedHandler`, bearer token mechanism, and security policy can customize how status codes are returned. Therefore, examine the status alongside response headers, security logs, and the active configuration.

This lesson focuses on finding the root cause and reproducing failures using Spring MVC Test / MockMvc.

## 1. Which Layers Does a Request Pass Through?

In a Spring MVC application using Spring Security, requests typically pass through the servlet filter chain before reaching `DispatcherServlet` and the controller.

    HTTP request
         |
         v
    Servlet container
         |
         v
    Spring Security FilterChainProxy
         |
         +--> Authentication (session, Basic, Bearer, ...)
         |
         +--> CSRF / CORS / other security filters
         |
         +--> URL-based authorization
         |
         v
    DispatcherServlet
         |
         v
    Handler mapping and controller
         |
         +--> Method security (@PreAuthorize, ...)
         |
         v
    Response

If a security filter rejects the request, the controller may never be called. For example, a POST request missing a CSRF token can be rejected inside the filter chain before Spring MVC looks up a handler. If the controller is invoked yet a method has `@PreAuthorize` and the user lacks the authority, method security can reject the call.

Therefore, when encountering 401 or 403, do not start by immediately changing DTOs or validation. First determine whether the request reached the controller at all.

## 2. Distinguishing 401 and 403

Under standard HTTP semantics:

| Status | Common meaning | Example |
| --- | --- | --- |
| 401 Unauthorized | No valid authentication credentials or authentication failed. | Missing token, expired token, wrong Basic credentials. |
| 403 Forbidden | The request is not allowed to perform the action. | Authenticated user lacks ROLE_ADMIN; missing or invalid CSRF token. |

### Cases Typically Leading to 401

- The endpoint requires authentication, yet the request lacks a valid session, Basic credentials, or Bearer token.
- Invalid username/password.
- Expired, invalid-signature, or rejected Bearer token.
- The authentication filter could not construct a valid `Authentication`.
- `AuthenticationEntryPoint` is configured to return 401 for unauthenticated requests.

Spring Security typically invokes `AuthenticationEntryPoint` when prompting the client to authenticate. For HTTP Basic or Bearer tokens, the response may include a `WWW-Authenticate` header describing the authentication scheme.

### Cases Typically Leading to 403

- The user is authenticated yet lacks the required authority.
- The URL requires ROLE_ADMIN while `Authentication` only holds ROLE_USER.
- Method security denies access.
- CSRF protection is enabled and a state-changing request lacks a token or sends an invalid one.
- Data access rules based on owner, tenant, or ACL deny access to the resource.
- `AccessDeniedHandler` is configured to return 403.

### Exceptions to This Rule

Spring Security distinguishes anonymous authentication from authenticated users when handling `AccessDeniedException`. An anonymous request that is denied may be delegated to `AuthenticationEntryPoint` and receive 401; an authenticated principal with insufficient permissions usually passes through `AccessDeniedHandler` and receives 403. Still, an application may customize its entry point, handler, or status responses.

Accordingly, do not conclude solely from the status code. Check:

- The `WWW-Authenticate` header.
- The response body or application-specific error code.
- Security debug logs.
- The `Authentication` in `SecurityContext`.
- Which filter or method security check rejected the request.

## 3. Checking URL-Based Authorization Rules

A Spring Security configuration can define permissions by HTTP method and path:

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public/**").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/reports/**")
                            .hasAnyRole("USER", "ADMIN")
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }

Read the configuration in exact order:

1. URLs under /public/** are accessible without logging in.
2. GET requests to /api/reports/** require role USER or ADMIN.
3. URLs under /api/admin/** require role ADMIN.
4. Remaining requests require authentication.

Request matchers are evaluated in declaration order; specific rules must come before broader rules that could match the same request. Placing a broad matcher such as /api/** before /api/admin/** lets the broad rule match first so the admin rule is never reached.

When diagnosing, check all three factors:

- The actual HTTP method.
- The actual path after context path, servlet path, or reverse proxy mapping.
- The first matching matcher selected in `SecurityFilterChain`.

Do not compare only the URL visible in a browser. A POST and a GET to the same path can be governed by two different policies.

## 4. Checking Roles and Authorities

Spring Security distinguishes between roles and authorities. The `hasRole("ADMIN")` method automatically prepends the `ROLE_` prefix during comparison, equivalent to requiring authority `ROLE_ADMIN`. The `hasAuthority("ROLE_ADMIN")` method compares the exact authority string specified.

Example:

    .requestMatchers("/api/admin/**").hasRole("ADMIN")

requires an `Authentication` holding the authority:

    ROLE_ADMIN

If a test creates a user with `roles`:

    @WithMockUser(username = "alice", roles = "ADMIN")

Spring Security Test creates the authority `ROLE_ADMIN`.

If using `authorities`:

    @WithMockUser(username = "alice", authorities = "ADMIN")

the created authority is `ADMIN`, without adding `ROLE_`. With `hasRole("ADMIN")`, these two configurations are not equivalent.

Comparison table:

| Check configuration | Required authority |
| --- | --- |
| hasRole("ADMIN") | ROLE_ADMIN |
| hasAnyRole("USER", "ADMIN") | ROLE_USER or ROLE_ADMIN |
| hasAuthority("invoice:read") | invoice:read |
| hasAuthority("ROLE_ADMIN") | ROLE_ADMIN |
| @PreAuthorize("hasRole('ADMIN')") | ROLE_ADMIN |
| @PreAuthorize("hasAuthority('invoice:read')") | invoice:read |

When a test unexpectedly receives 403, inspect the actual authorities in `Authentication` rather than just reading role names in business docs.

## 5. Reproducing 401 with MockMvc

To test the security filter chain, the test must actually wire Spring Security's filters into MockMvc. With Spring Boot, `@AutoConfigureMockMvc` normally configures the filter chain in MockMvc unless filter registration is disabled.

Example:

    @SpringBootTest
    @AutoConfigureMockMvc
    class ReportSecurityTest {

        @Autowired
        MockMvc mockMvc;

        @Test
        void anonymousUserCannotReadProtectedReport() throws Exception {
            mockMvc.perform(get("/api/reports/42"))
                    .andExpect(status().isUnauthorized());
        }
    }

This test sends a request with no authentication. If the endpoint requires a logged-in user and the entry point returns 401, the assertion passes.

If the application uses form login, an anonymous response may be a redirect to the login page instead of 401. In that case, assert the status and `Location` matching the configuration. For REST APIs, entry points are usually configured to return 401 so clients get an explicit response.

### Verifying Authentication Headers

With HTTP Basic or Bearer, a 401 response typically includes `WWW-Authenticate`. You can assert:

    mockMvc.perform(get("/api/reports/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().exists("WWW-Authenticate"));

The exact header depends on the authentication scheme and entry point configuration. Do not hard-code Basic if the endpoint actually uses Bearer.

## 6. Reproducing 403 Due to Missing Authority

Spring Security Test provides `@WithMockUser` to populate a simulated `Authentication` for a test method. A test can verify an authenticated user lacking sufficient permissions:

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void userRoleCannotAccessAdminEndpoint() throws Exception {
        mockMvc.perform(get("/api/admin/users"))
                .andExpect(status().isForbidden());
    }

If the endpoint requires `ROLE_ADMIN`, a user with only `ROLE_USER` is rejected with 403.

Valid permission test:

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanAccessAdminEndpoint() throws Exception {
        mockMvc.perform(get("/api/admin/users"))
                .andExpect(status().isOk());
    }

These two tests form a clear pair: a user lacking permission is denied, and a user with permission is allowed. If the controller also depends on a service, stub the service data accordingly so the test does not fail for another reason after passing security.

## 7. Using the `user()` Request Post-Processor to Control the Principal

Instead of placing `@WithMockUser` on the method, you can attach a user directly to the request:

    mockMvc.perform(get("/api/admin/users")
                    .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());

This is convenient when a single test method sends multiple requests with different principals.

If the endpoint checks a custom authority:

    mockMvc.perform(get("/api/invoices")
                    .with(user("alice")
                            .authorities(
                                    new SimpleGrantedAuthority("invoice:read"))))
            .andExpect(status().isOk());

Use `roles(...)` when the security config uses `hasRole`/`hasAnyRole`. Use `authorities(...)` when the config uses fine-grained permissions such as `invoice:read`, `order:approve`, or `tenant:manage`.

Note: `user(...)` and `@WithMockUser` populate `Authentication` for the request/test. They are useful for testing authorization. They do not verify the real login flow, whether passwords are checked, or whether a JWT has a valid signature.

## 8. Distinguishing Authorization Tests from Real Authentication Tests

There are three different test categories:

| Goal | Appropriate approach |
| --- | --- |
| Which role/authority allows a user to call an endpoint? | @WithMockUser or the user(...) request post-processor. |
| Are HTTP Basic credentials verified through the filter? | Use httpBasic(...) with a real test AuthenticationManager/UserDetailsService and PasswordEncoder or matching config. |
| Is a Bearer token parsed, signature-verified, and checked for claims? | Send the token through the Bearer filter; use a mock JwtDecoder or real test keys/tokens depending on the goal. |

Example testing HTTP Basic:

    @Test
    void validBasicCredentialsCanAccessEndpoint() throws Exception {
        mockMvc.perform(get("/api/profile")
                        .with(httpBasic("alice", "password")))
                .andExpect(status().isOk());
    }

This test is meaningful when the security chain is configured with HTTP Basic and `AuthenticationManager` has matching users/passwords. If you only use `@WithMockUser`, the Basic authentication filter is never exercised.

For a JWT resource server, the `jwt()` request post-processor can construct a `JwtAuthenticationToken` to test authorization based on claims and authorities:

    mockMvc.perform(get("/api/invoices")
                    .with(jwt().authorities(
                            new SimpleGrantedAuthority("invoice:read"))))
            .andExpect(status().isOk());

`jwt()` is useful for testing authorization rules against an already-constructed principal/claims. It does not test token decoding, signature verification, issuer, audience, or token expiration. To test those steps, send a Bearer token through the filter chain with an appropriate `JwtDecoder`, either mocking the decoder in a slice test or using real test keys/tokens in an integration test.

## 9. CSRF: A Common Reason POST/PUT/DELETE Receive 403

CSRF protection is enabled by default in many Spring Security configurations for servlet applications. State-changing requests such as POST, PUT, PATCH, and DELETE typically require a valid CSRF token. GET, HEAD, OPTIONS, and TRACE are treated as safe methods by convention and normally do not require a token.

A POST test can return 403 even when the user is logged in and has the right role:

    @Test
    @WithMockUser(roles = "ADMIN")
    void postWithoutCsrfTokenIsRejected() throws Exception {
        mockMvc.perform(post("/api/admin/users")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Lan\"}"))
                .andExpect(status().isForbidden());
    }

If the test's goal is to verify the controller creates data successfully, add a CSRF token:

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanCreateUserWithCsrfToken() throws Exception {
        mockMvc.perform(post("/api/admin/users")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Lan\"}"))
                .andExpect(status().isCreated());
    }

The static `csrf()` request post-processor is provided by Spring Security Test. It attaches a valid token compatible with the test support's CSRF mechanism.

You can also test an invalid token:

    mockMvc.perform(post("/api/admin/users")
                    .with(csrf().useInvalidToken())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"name\":\"Lan\"}"))
            .andExpect(status().isForbidden());

You can send the token as a header if the application/client uses headers:

    mockMvc.perform(post("/api/admin/users")
                    .with(csrf().asHeader())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"name\":\"Lan\"}"))
            .andExpect(status().isCreated());

The default header name depends on `CsrfTokenRepository`. If the application uses a custom repository, configure the request post-processor or request token using the exact name/header the application expects.

Do not disable CSRF just to make a test pass if the application uses session/cookie authentication and faces CSRF risks. For stateless APIs using Bearer tokens in the `Authorization` header, the CSRF policy may differ; configure it based on how browsers send credentials and the application's threat model.

## 10. Distinguishing CSRF 403 from Access-Permission 403

Both cases can return 403, yet their causes and fixes differ.

| Symptom | CSRF rejection | Missing permission |
| --- | --- | --- |
| Request method | Usually POST/PUT/PATCH/DELETE. | Can be any method. |
| Authentication | May already be logged in with the right role. | Usually authenticated yet lacks sufficient authority. |
| CSRF token | Missing, invalid, or sent in the wrong place. | May be completely valid. |
| URL/Method rule | May allow the current user. | Rule requires a higher role/authority. |
| Rejection point | CSRF filter in the filter chain. | Authorization filter or method security. |
| How to reproduce | Omit token or send bad token; then add csrf() to compare. | Use a user lacking authority; then switch to the proper role. |

An effective diagnostic technique is sending two identical requests, changing only one variable:

1. Keep the user and payload identical, and send the POST without a CSRF token.
2. Re-send the exact same request with `csrf()`.
3. If the second request passes through, the original error was CSRF.
4. If the second request still receives 403, inspect URL authorization, method security, and data-level permissions.

Do not add a new role, a new token, and change the payload all in the same attempt. Changing one variable at a time makes the cause easy to isolate.

## 11. Method Security Can Reject Requests After Reaching the Controller

An endpoint may pass URL matchers yet still be blocked at the method level by `@PreAuthorize` or `@PostAuthorize`.

    @Service
    class InvoiceService {

        @PreAuthorize("hasAuthority('invoice:approve')")
        public void approve(long invoiceId) {
            // Business operation.
        }
    }

Method security must be enabled in configuration:

    @Configuration
    @EnableMethodSecurity
    class MethodSecurityConfig {
    }

If the user can access the URL yet lacks `invoice:approve`, the service call is rejected. For an MVC request, the exception can be handled and return 403 depending on exception translation configuration and where the method is invoked.

Test:

    @Test
    @WithMockUser(authorities = "invoice:read")
    void readerCannotApproveInvoice() throws Exception {
        mockMvc.perform(post("/api/invoices/42/approve")
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

This test supplies a CSRF token so it is not stopped at the CSRF filter; the user has only `invoice:read`, so method security can deny the approve operation.

Test for valid permissions:

    @Test
    @WithMockUser(authorities = {"invoice:read", "invoice:approve"})
    void approverCanApproveInvoice() throws Exception {
        mockMvc.perform(post("/api/invoices/42/approve")
                        .with(csrf()))
                .andExpect(status().isNoContent());
    }

When method security is applied at the service layer, you can also write unit/integration tests directly against the service. A MockMvc test additionally confirms the entire request flows through the filter chain and controller before method security is enforced.

## 12. Request Data Can Affect Authorization Decisions

Not every 403 is caused by a missing role. Many applications evaluate permissions using request data:

- A resource ID in the path belongs to another user.
- A tenant ID in a header or token does not match the resource.
- An organization ID in the request body falls outside the user's scope.
- An owner ID, project ID, or account ID is looked up from the database.
- Business state forbids the user from performing the action.
- The resource's ACL or permission record disallows the operation.

Example service checking invoice ownership:

    @Service
    class InvoiceAccessService {

        private final InvoiceRepository repository;

        InvoiceAccessService(InvoiceRepository repository) {
            this.repository = repository;
        }

        @PreAuthorize("@invoiceAccessService.canRead(authentication, #invoiceId)")
        public Invoice findReadable(long invoiceId) {
            return repository.findById(invoiceId).orElseThrow();
        }

        public boolean canRead(Authentication authentication, long invoiceId) {
            Invoice invoice = repository.findById(invoiceId).orElse(null);
            if (invoice == null) {
                return false;
            }
            return invoice.getOwnerUsername().equals(authentication.getName());
        }
    }

A user may hold role `USER` yet only be permitted to read invoices they own. If a request hits `/api/invoices/42` and invoice 42 belongs to another user, method security denies access even though the user's role is valid.

When testing this scenario, control both the principal and the resource data:

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void userCannotReadAnotherUsersInvoice() throws Exception {
        // Test fixture creates invoice 42 owned by bob.
        mockMvc.perform(get("/api/invoices/42"))
                .andExpect(status().isForbidden());
    }

If the test fails to create the matching invoice data, the outcome may be 404 or another error instead of 403. That does not prove authorization is wrong; it may simply indicate the fixture does not match the scenario under test.

Distinguish clearly:
- Resource does not exist: usually 404.
- Resource exists yet user lacks permission: may be 403.
- Application intentionally conceals resource existence: may return 404 instead of 403.

This is an application security decision and must be tested according to the chosen contract.

## 13. Invalid Request Data Is Usually Not 401/403

A malformed payload, missing field, or Bean Validation failure is normally handled at the MVC layer and returns 400 Bad Request or the application's dedicated validation status.

For example:
- Malformed JSON: usually 400.
- Unsupported Content-Type: usually 415 Unsupported Media Type.
- Missing required request parameter: usually 400.
- DTO violating `@Valid`: usually 400 under the default exception handler or equivalent config.
- Unsupported HTTP method: usually 405.
- Non-existent mapping: usually 404.

When receiving 401/403, check whether a security filter rejected the request before binding or validation ran. An invalid request payload might never reach the controller if the filter chain already rejected it earlier.

However, request data can be used inside authorization. For example, a wrong `tenantId` or `resourceId` can lead to 403. Therefore, identify which data serves as input to binding/validation and which data feeds access decisions.

## 14. Configuring MockMvc Properly to Test Spring Security

A MockMvc test only exercises the security filter chain if the filter chain is actually registered with MockMvc.

### Spring Boot with `@AutoConfigureMockMvc`

    @SpringBootTest
    @AutoConfigureMockMvc
    class SecurityIntegrationTest {
        @Autowired
        MockMvc mockMvc;
    }

By default, Spring Boot adds servlet filters to MockMvc. If a test uses `addFilters = false`, the security filter chain will not run and requests may go straight to MVC.

### Building MockMvc Manually from `WebApplicationContext`

When building MockMvc manually, apply the Spring Security configurer:

    @Autowired
    WebApplicationContext context;

    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(context)
                .apply(springSecurity())
                .build();
    }

The `springSecurity()` configurer connects the Spring Security filter chain to MockMvc. Omitting this step prevents tests from reproducing 401/403 responses returned by the real application.

### Standalone Setup

`standaloneSetup(controller)` builds MVC infrastructure solely around the chosen controller. It does not automatically load the application's full security filter chain. When diagnosing actual security configuration, prefer `webAppContextSetup` or a Spring Boot test with the filter chain loaded.

Filters can be added manually to standalone MockMvc, but then the test must manage the entire filter chain and filter ordering itself. That approach easily misses production configuration and is only suitable for specific reasons.

## 15. Checking CORS and Preflight Requests

Some browser requests begin with a CORS preflight `OPTIONS` request. If the security config blocks preflight requests or the CORS configuration disallows the needed origin/method/header, requests may receive 401/403 or browsers may report CORS errors.

Preflight example:

    mockMvc.perform(options("/api/reports")
                    .header("Origin", "https://app.example.test")
                    .header("Access-Control-Request-Method", "POST")
                    .header("Access-Control-Request-Headers", "content-type,authorization"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "Access-Control-Allow-Origin",
                    "https://app.example.test"));
    
Actual status and headers depend on the CORS configuration. Check:

- Is the origin in the allowed origins list?
- Is the POST method in the allowed methods list?
- Are the `Authorization` or `Content-Type` headers allowed?
- Does the CORS filter/processor run before the relevant security authorization checks?
- Is `OPTIONS` inadvertently requiring authentication?

CORS is a browser policy. A request via `curl` or MockMvc does not fully reproduce browser response blocking, yet it can verify preflight responses and headers returned by the server.

## 16. Multiple `SecurityFilterChain` Beans and Mismatched Matchers

An application may declare multiple `SecurityFilterChain` beans, such as one chain for APIs and another for form login. Spring selects the first chain whose `securityMatcher` matches the request; subsequent chains do not run for that request.

Example:

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public/**").permitAll()
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth -> oauth.jwt())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }

If an API request fails to match the intended chain, it may fall into another chain and receive an unexpected status or redirect.

When diagnosing, check:
- Each chain's `securityMatcher`.
- The `@Order` of the chains.
- The actual URL, context path, and servlet path.
- Which chain matches the request first.
- Which authentication mechanism is configured in that chain.

Do not inspect only a single `authorizeHttpRequests` block; examine the entire structure of all `SecurityFilterChain` beans in the application context.

## 17. Enabling Logs to Find Which Filter Rejected the Request

When it is unclear which filter returned 401/403, enable Spring Security logging in a test profile or diagnostic configuration:

    logging.level.org.springframework.security=DEBUG

Logs can reveal:
- Which `SecurityFilterChain` was selected.
- Which request matchers were evaluated.
- Where authentication was created or failed.
- Which authority caused an access decision denial.
- Whether the CSRF filter detected a missing or invalid token.
- Whether `ExceptionTranslationFilter` invoked `AuthenticationEntryPoint` or `AccessDeniedHandler`.

Do not leave DEBUG enabled across production if logs could expose sensitive information or generate excessive volume. Use a test/dev profile and disable it after diagnosing.

## 18. 401/403 Diagnostic Checklist

When a MockMvc or API test receives an unexpected 401/403, walk through this sequence:

1. Verify the exact HTTP method and URL sent by the test.
2. Confirm MockMvc has the Spring Security filter chain attached.
3. Identify the first `SecurityFilterChain` matching the request.
4. Check whether the request has an authentication.
5. If using Basic/Bearer, check credentials/tokens, headers, and the authentication filter.
6. Check actual authorities, distinguishing the `ROLE_` prefix from custom authorities.
7. Check request matchers by method/path and declaration order.
8. For POST/PUT/PATCH/DELETE, check the CSRF token.
9. Check method security such as `@PreAuthorize` and `@PostAuthorize`.
10. Check whether resource data, owner, tenant, or ACL affects the access decision.
11. Check CORS preflight if the failure occurs only in browsers.
12. Inspect response headers/body and security logs to identify the entry point or access denied handler.

## 19. Common Testing Mistakes

**Using `@WithMockUser` yet still receiving 403 on POST.**

The user is authenticated, yet the request still lacks a CSRF token. Add `.with(csrf())` if the test needs to send a valid request past the CSRF filter.

**Using `roles("ADMIN")` yet still getting denied.**

Check whether the endpoint uses `hasRole("ADMIN")` or `hasAuthority("ADMIN")`/`hasAuthority("ROLE_ADMIN")`. `roles(...)` prepends `ROLE_`; `authorities(...)` does not.

**The test gets 200 while the real app returns 401.**

MockMvc may not have security filters registered, or the test uses `standaloneSetup`. Use `webAppContextSetup(...).apply(springSecurity())` or Boot configuration that retains the filter chain.

**Using `@Mock` on a service and assuming it replaced the bean in the Spring context.**

`@Mock` creates a mock only on the test instance. It does not replace the bean injected into the controller. Use `@MockitoBean`/`@MockBean` per version or appropriate test bean configuration.

**Adding a new role to fix a CSRF failure.**

CSRF is token validation, not role authorization. Adding a role will not fix a request missing a token.

**Receiving 404 instead of 403 when testing ownership.**

The resource may not have been created in the fixture, or the application intentionally hides inaccessible resources. Prepare the right data and verify the application's 404/403 contract.

**Testing JWT with `jwt()` and concluding real tokens are valid.**

`jwt()` creates a simulated `Authentication` for authorization. It does not verify the signature, issuer, audience, or expiration of a real token.

**Editing only the controller when a security filter blocked the request.**

If the controller was never invoked, changing validation or controller mappings will not fix the cause. Locate the filter, matcher, CSRF check, or authentication entry point that denied the request.

## 20. Testing Workflow by Cause

Tests can be organized into focused groups:

| Test group | Request setup | Expected outcome |
| --- | --- | --- |
| Anonymous | No authentication | 401 or login redirect per configuration. |
| Authenticated yet missing role | user("alice").roles("USER") | 403 on endpoints requiring ADMIN. |
| Matching role | user("admin").roles("ADMIN") | 2xx per endpoint. |
| POST missing CSRF | Valid user, no csrf() | 403 when CSRF is enabled. |
| POST with CSRF | Valid user and csrf() | Request passes CSRF; outcome depends on permissions and data. |
| Invalid token/credentials | Send bad credentials/token through real filter | 401 per authentication entry point. |
| Not resource owner | Valid user, resource owned by another user | 403 or 404 per application policy. |
| Invalid payload | Valid authentication and permissions, invalid body | Usually 400/415, not 401/403. |

Keep each test focused on a single cause. For example, when testing CSRF, provide a user with sufficient roles and a valid payload; when testing roles, provide a valid CSRF token for POST requests. This prevents a test from being blocked by another security layer before reaching the layer you intend to test.

## Conclusion

401 and 403 typically occur when a request is rejected in the Spring Security filter chain or by method security. 401 usually relates to invalid or missing authentication; 403 usually relates to authorities, CSRF, or resource access permissions. However, the actual status depends on the entry point, access denied handler, and application policy.

To diagnose with MockMvc, ensure security filters are actually attached to the test, then inspect method/path, authentication, authorities, CSRF tokens, method security, and owner/tenant/ACL data. Use `@WithMockUser` or `user(...)` for authorization tests; use real Basic/Bearer flows when testing authentication. Separate security failures from binding/validation errors so you fix the responsible layer.
