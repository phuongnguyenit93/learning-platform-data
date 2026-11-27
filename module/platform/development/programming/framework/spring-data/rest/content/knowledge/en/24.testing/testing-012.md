# Testing Authorization, CSRF, and CORS with Spring Security Test

Spring Data REST automatically publishes repositories as REST endpoints, but an endpoint appearing over HTTP does not mean every user is allowed to access it. The API must define who can read, create, edit, or delete resources; whether write requests require a CSRF token; and which paths frontends on other origins are permitted to call.

Spring Security Test helps verify those rules directly at the HTTP layer using MockMvc. This lesson covers setting up tests, simulating users and authorities, testing CSRF tokens, sending CORS preflight requests, and asserting rejected requests.

## 1. Distinguishing Authentication, Authorization, CSRF, and CORS

These four concepts answer different questions:

| Concept | Question | Example |
|---|---|---|
| Authentication | Who does the request belong to? | Session, HTTP Basic, JWT |
| Authorization | What is that user allowed to do? | ROLE_READER can GET, ROLE_ADMIN can POST |
| CSRF protection | Was the state-changing request sent from another site abusing auto-attached credentials? | POST must carry a valid CSRF token |
| CORS | Is the browser allowed to let JavaScript on this origin read responses from the API? | Allow https://app.example.com to call the API |

Do not substitute one mechanism for another:

- CORS does not authenticate users and does not authorize endpoints.
- CSRF does not decide whether a user holds the required role.
- Successful authentication does not mean the request is authorized to perform an operation.
- A request whose response the browser blocks via CORS may still have reached the server and caused side effects if the server processed that request.

In particular, CORS is a browser-enforced policy. A `curl` command or a backend service calling the API is not constrained by browser CORS. Therefore, CORS is not an API security perimeter against all clients.

## 2. Setting Up Spring Security Test

In a Spring Boot application, test dependencies are typically declared as:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-rest")
    implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Use dependency versions managed by Spring Boot dependency management to avoid mixing incompatible Spring Security versions.

Key components of Spring Security Test:

- `@WithMockUser`: creates a SecurityContext with a mock user for the test.
- `@WithUserDetails`: loads a user from the real UserDetailsService.
- `user()` and `anonymous()`: attach a user or anonymous principal to an individual MockMvc request.
- `csrf()`: generates a valid CSRF token or an invalid token.
- `jwt()`: simulates JWT authentication when the application uses OAuth2 Resource Server.
- `springSecurity()`: integrates the Spring Security filter chain into MockMvc when building MockMvc manually.

For tests using `@SpringBootTest` and `@AutoConfigureMockMvc`, Spring Boot normally configures MockMvc with the filter chain in the application context. If you construct MockMvc manually with `MockMvcBuilders`, you must apply the Spring Security configurer so filters run during tests.

Example:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CustomerSecurityIntegrationTest {

    @Autowired
    MockMvc mockMvc;
}
~~~

Integration tests should use the application's real security configuration. If you only test a controller with standalone MockMvc without attaching the Security filter chain, passing results do not prove endpoints are protected properly in the running application.

## 3. Declaring Authorization Rules for Spring Data REST

Suppose a repository exposes resources at `/customers` and item resources at `/customers/{id}`. Illustrative rules:

- READER can GET lists and details.
- ADMIN can GET, POST, PUT, PATCH, and DELETE.
- Unauthenticated users cannot access endpoints requiring login.

~~~java
@Configuration
@EnableMethodSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/customers", "/customers/**")
                    .hasAnyRole("READER", "ADMIN")
                .requestMatchers(HttpMethod.POST,
                    "/customers", "/customers/**")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.PUT,
                    "/customers/**")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.PATCH,
                    "/customers/**")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.DELETE,
                    "/customers/**")
                    .hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This is an illustrative configuration for an API using HTTP Basic. Actual paths must match the application's base path, repository paths, and export settings. If using session login or bearer tokens, the authentication mechanism and corresponding test setup will differ.

`hasRole("ADMIN")` checks the authority `ROLE_ADMIN` by default. When using `hasAuthority("CUSTOMER_WRITE")`, Spring Security compares the exact declared authority name without adding a `ROLE_` prefix.

`@EnableMethodSecurity` enables method security so annotations like `@PreAuthorize` are enforced. It can be used to protect repository or service operations according to business rules. When combining URL authorization and method authorization, tests must verify both layers work.

Do not rely on the frontend hiding a Delete button to protect an operation. Clients can call URLs directly; the server must reject unauthorized requests.

## 4. Simulating Users and Roles in Tests

### 4.1. Using @WithMockUser

Example testing that READER can read the collection:

~~~java
@Test
@WithMockUser(username = "reader", roles = "READER")
void readerCanReadCustomers() throws Exception {
    mockMvc.perform(get("/customers"))
        .andExpect(status().isOk());
}
~~~

`@WithMockUser` places a user in the SecurityContext for the test. It does not create an account in the database and does not test the real login flow. It is a fast way to test authorization after authentication is simulated.

Testing that READER cannot create a Customer:

~~~java
@Test
@WithMockUser(username = "reader", roles = "READER")
void readerCannotCreateCustomer() throws Exception {
    mockMvc.perform(post("/customers")
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Nguyen An",
                  "email": "an@example.com"
                }
                """))
        .andExpect(status().isForbidden());
}
~~~

The request includes a valid CSRF token so the test focuses on authorization. If the token were omitted, the request could be rejected by the CSRF filter before checking roles; the test would then fail to prove that READER cannot POST.

### 4.2. Using exact authorities

If the application does not use a role prefix, declare authorities directly:

~~~java
@Test
@WithMockUser(authorities = "CUSTOMER_READ")
void customerReadAuthorityCanRead() throws Exception {
    mockMvc.perform(get("/customers"))
        .andExpect(status().isOk());
}
~~~

If security rules require `hasRole("READER")`, use `roles = "READER"` or authority `ROLE_READER`. Avoid mixing up roles and authorities, as that is a frequent cause of unexpected 403s in tests.

### 4.3. Using real users from UserDetailsService

When you need to test how the application loads users, roles, and account states from the database, you can use:

~~~java
@Test
@WithUserDetails("reader@example.com")
void persistedReaderCanReadCustomers() throws Exception {
    mockMvc.perform(get("/customers"))
        .andExpect(status().isOk());
}
~~~

The corresponding user must exist in test data and `UserDetailsService` must be able to load that user. Tests must prepare data before running, and clean up or use transactions per the application's testing strategy.

### 4.4. Distinguishing 401 and 403

- 401 Unauthorized: request is unauthenticated or credentials are invalid; server requires authentication.
- 403 Forbidden: request is authenticated but principal lacks sufficient permissions, or was rejected by a filter such as CSRF.

Actual statuses also depend on the authentication entry point and access denied handler. With HTTP Basic as shown above, unauthenticated requests typically receive 401. With form login, unauthenticated requests may receive a 302 redirect to the login page. Verify against the application's exact contract.

## 5. Testing CSRF Tokens

CSRF (Cross-Site Request Forgery) happens when a browser automatically sends a user's credentials, such as session cookies, along with a request forged from another website. An attacker can exploit an active login session to trigger state-changing server requests.

Spring Security enables CSRF protection by default for state-changing requests such as POST, PUT, PATCH, and DELETE. Safe methods like GET, HEAD, TRACE, and OPTIONS are excluded from default CSRF protection.

A CSRF token is additional proof that a write request originated through the application's expected flow. The token must be sent back by the client as configured by the server, typically via a request parameter or header.

### 5.1. Requests with a valid token

Spring Security Test provides the `csrf()` request post-processor:

~~~java
@Test
@WithMockUser(roles = "ADMIN")
void adminCanCreateCustomerWithCsrfToken() throws Exception {
    mockMvc.perform(post("/customers")
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Nguyen An",
                  "email": "an@example.com"
                }
                """))
        .andExpect(status().isCreated());
}
~~~

This example assumes a valid payload and an allowed repository resource creation. If the endpoint has validation or a different response contract, adjust body and assertions to fit the application.

### 5.2. Sending the token via header

Frontends commonly send CSRF tokens in a header. You can test this approach with:

~~~java
@Test
@WithMockUser(roles = "ADMIN")
void acceptsCsrfTokenInHeader() throws Exception {
    mockMvc.perform(post("/customers")
            .with(csrf().asHeader())
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Nguyen An",
                  "email": "an@example.com"
                }
                """))
        .andExpect(status().isCreated());
}
~~~

`csrf().asHeader()` places the token in the header matching the name used by the request post-processor and Spring Security configuration. If the application renames the header or uses a custom token repository, verify the exact header name.

### 5.3. Missing or invalid token

Testing a write request with no token:

~~~java
@Test
@WithMockUser(roles = "ADMIN")
void rejectsPostWithoutCsrfToken() throws Exception {
    mockMvc.perform(post("/customers")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Nguyen An",
                  "email": "an@example.com"
                }
                """))
        .andExpect(status().isForbidden());
}
~~~

Testing an invalid token:

~~~java
@Test
@WithMockUser(roles = "ADMIN")
void rejectsInvalidCsrfToken() throws Exception {
    mockMvc.perform(post("/customers")
            .with(csrf().useInvalidToken())
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Nguyen An",
                  "email": "an@example.com"
                }
                """))
        .andExpect(status().isForbidden());
}
~~~

These tests should use a user who already has ADMIN privileges so you confirm CSRF is the reason for rejection. Using an unprivileged user allows multiple security layers to reject the request, obscuring which filter is being tested.

Also test PUT, PATCH, and DELETE because they are write methods. One passing POST test does not prove all write methods are properly protected.

### 5.4. When can CSRF be disabled?

Do not disable CSRF simply because an API returns JSON or is called by a SPA frontend. If the browser authenticates using session cookies or credentials automatically attached by the browser, requests remain vulnerable to CSRF.

An API that solely accepts bearer tokens in the Authorization header, without relying on browser-auto-sent credentials, has a different threat model and may configure CSRF accordingly for that security chain. Decisions must rest on the actual authentication mechanism, how tokens are stored, and whether browsers automatically attach credentials.

If using cookies to share a CSRF token with a SPA, you can configure `CookieCsrfTokenRepository`. Example:

~~~java
http.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieCsrfTokenRepository.withHttpOnlyFalse()
    )
);
~~~

Token handling in Spring Security 6 may require configuring a request handler suited for SPAs and your exact version. Do not assume reading the cookie alone suffices to send back a valid token; verify cookie name, header name, token masking behavior, and actual responses. Cookie tokens are typically read by the frontend to populate a header; session cookies still need to be sent by the browser under appropriate cookie policies.

## 6. Testing CORS Preflight

CORS (Cross-Origin Resource Sharing) controls whether a browser permits JavaScript on one origin to read responses from another origin. An origin consists of scheme, host, and port. For example:

- `https://app.example.com`
- `https://api.example.com`

These two URLs are two different origins even though they share the same root domain.

A cross-origin request may be sent directly by the browser or trigger a preflight OPTIONS request first. Preflight usually occurs when a request uses a method or header outside the simple-request category, such as POST with `Content-Type: application/json` or custom header `X-XSRF-TOKEN`.

### 6.1. Configuring CORS

You can declare a `CorsConfigurationSource` and enable CORS in `SecurityFilterChain`:

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();

    config.setAllowedOrigins(
        List.of("https://app.example.com")
    );
    config.setAllowedMethods(
        List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
    );
    config.setAllowedHeaders(
        List.of("Authorization", "Content-Type", "X-XSRF-TOKEN")
    );
    config.setExposedHeaders(
        List.of("Location", "ETag", "Link")
    );
    config.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", config);

    return source;
}
~~~

Key options:

- allowedOrigins: specific origins allowed to call the API.
- allowedMethods: methods the browser is permitted to use cross-origin.
- allowedHeaders: headers the browser is permitted to send.
- exposedHeaders: response headers JavaScript is permitted to read.
- allowCredentials: permits the browser to send credentials in cross-origin requests.

When credentials are enabled, do not use wildcard `*` for allowed origins. Specify concrete origins or design an appropriate origin-checking mechanism. If clients need to read `Location`, `ETag`, or `Link` from Spring Data REST responses, expose those headers explicitly; the server sending a header does not automatically allow JavaScript to read it.

CORS must be processed before authorization requiring login, because preflight requests usually carry no session cookies or bearer tokens. With Spring Security, enable `http.cors(...)` and supply a CORS configuration so the filter handles preflight ahead of regular authentication.

Do not indiscriminately open all OPTIONS endpoints just to make CORS work. The CORS filter must validate Origin, requested method, and requested headers against configuration.

### 6.2. Testing preflight for an allowed origin

Use MockMvc to send OPTIONS with the headers a browser typically sends:

~~~java
@Test
void allowsPreflightFromConfiguredOrigin() throws Exception {
    mockMvc.perform(options("/customers")
            .header(HttpHeaders.ORIGIN, "https://app.example.com")
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "POST"
            )
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "content-type,x-xsrf-token"
            ))
        .andExpect(status().isOk())
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
            "https://app.example.com"
        ))
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
            containsString("POST")
        ))
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS,
            allOf(
                containsString("content-type"),
                containsString("x-xsrf-token")
            )
        ));
}
~~~

Depending on version and configuration, the preflight status may reflect the application's CORS implementation. Verify that responses for valid origins include Allow-Origin, methods, and headers matching the request. If the application configures credentials, also check that `Access-Control-Allow-Credentials` is `true`.

### 6.3. Testing a disallowed origin

~~~java
@Test
void rejectsPreflightFromUntrustedOrigin() throws Exception {
    mockMvc.perform(options("/customers")
            .header(HttpHeaders.ORIGIN, "https://evil.example")
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "POST"
            ))
        .andExpect(status().isForbidden())
        .andExpect(header().doesNotExist(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN
        ));
}
~~~

This test confirms untrusted origins receive no access-allowing header. If the application uses a custom CORS processor or error handler, the exact status may vary; keep the contract clear and confirm the browser is prevented from reading responses.

### 6.4. Testing the actual request

A passing preflight does not prove the actual request passes authorization and CSRF. Also test a request carrying a valid Origin:

~~~java
@Test
@WithMockUser(roles = "READER")
void allowsActualReadFromConfiguredOrigin() throws Exception {
    mockMvc.perform(get("/customers")
            .header(HttpHeaders.ORIGIN, "https://app.example.com"))
        .andExpect(status().isOk())
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
            "https://app.example.com"
        ));
}
~~~

For write requests, verify simultaneously:

- Is the Origin allowed?
- Are the method and headers allowed?
- Is the user authenticated and authorized?
- Is the CSRF token valid if CSRF protection is enabled?
- Does the request actually create or update data accurately?

CORS does not replace authorization or CSRF assertions.

## 7. Testing a JWT Resource Server

If the API uses an OAuth2 Resource Server instead of HTTP Basic, you can simulate JWT authentication with Spring Security Test:

~~~java
@Test
void readerJwtCanReadCustomers() throws Exception {
    mockMvc.perform(get("/customers")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("ROLE_READER")
            )))
        .andExpect(status().isOk());
}
~~~

This creates an authentication in tests without signing and transmitting a real JWT. It works well for testing authorization after the token is validated and mapped to authorities.

It does not verify signatures, issuer, audience, expiry, or fetching public keys from an identity provider. Those parts require separate tests for decoders or security integration.

If the API uses scopes like `customers.read`, authorities are typically mapped to `SCOPE_customers.read`. Simulate the exact authority checked by production rules, for example:

~~~java
.with(jwt().authorities(
    new SimpleGrantedAuthority("SCOPE_customers.read")
))
~~~

Do not use role `READER` in tests if production tokens only carry scopes and no converter maps scopes into that role.

## 8. Recommended Test Matrix

A Spring Data REST security integration suite can include:

| Scenario | Simulation | Expected result |
|---|---|---|
| Anonymous reads protected resource | No user supplied | 401 or redirect per entry point |
| READER reads collection | `@WithMockUser(roles = "READER")` | 200 |
| READER creates resource | READER + valid CSRF | 403 |
| ADMIN creates resource | ADMIN + valid CSRF + valid payload | 201 or endpoint-specific status |
| ADMIN POST missing CSRF | ADMIN, no token | 403 |
| ADMIN POST invalid token | ADMIN + invalid token | 403 |
| ADMIN PUT/PATCH/DELETE | ADMIN + valid token | Succeeds per contract |
| Allowed origin preflight | OPTIONS + valid Origin | Matching Allow-Origin/Methods/Headers |
| Disallowed origin | OPTIONS + Origin outside allowlist | No Allow-Origin |
| JWT missing authority | JWT with insufficient scope/role | 403 |
| Protected repository method | Valid authentication rejected by method security | 403 |

Alongside statuses, verify important headers:

- Access-Control-Allow-Origin
- Access-Control-Allow-Methods
- Access-Control-Allow-Headers
- Access-Control-Allow-Credentials
- Access-Control-Expose-Headers
- Vary: Origin when responses vary by origin

If tests inspect response bodies, ensure data is unchanged when requests are rejected. For example, after a POST rejected by CSRF, the repository must not contain a new entity. After an unauthorized DELETE, the resource must still exist.

## 9. Common Mistakes When Writing Spring Security Tests

**POST test returns 403 even though user has ADMIN:** the CSRF token may be missing. Add `.with(csrf())` when testing authorization. If testing CSRF itself, omit the token and assert rejection.

**Using `roles = "ADMIN"` yet rule still rejects:** check whether the rule uses `hasRole("ADMIN")` or `hasAuthority("ADMIN")`. Roles carry the `ROLE_` prefix by default.

**GET test returns 401:** check whether the test attached `@WithMockUser`, `user()`, or JWT; also check URL matchers and the authentication entry point.

**Preflight OPTIONS requires login:** check `http.cors(...)`, `CorsConfigurationSource`, and CORS filter ordering. Preflight must be handled ahead of regular authorization.

**CORS test passes yet browser still cannot read response:** check the exact origin including scheme/host/port, credentials, requested headers, exposed headers, and Vary. `Access-Control-Allow-Origin` must match the frontend's origin accurately.

**Frontend sends Authorization yet preflight fails:** add Authorization to allowed headers if the API uses this header. Also check Content-Type and custom CSRF headers.

**Using wildcard origin with credentials:** browsers reject this configuration. Specify explicit origins or validate origins against an allowlist.

**Confusing CORS with authentication:** `curl` reaching the API does not mean browsers are allowed to read responses. Conversely, CORS permitting an origin does not mean the user is logged in or authorized.

**Disabling CSRF to make tests pass:** this can hide vulnerabilities in cookie/session-based applications. Configure according to the authentication model and test proper token flows.

**Using only `@WithMockUser` to conclude login works:** the annotation does not execute the login flow and does not verify passwords, session creation, or JWT signatures. Write separate tests for the authentication mechanism.

## 10. Pre-Release Checklist

1. Repository resources have explicit GET/POST/PUT/PATCH/DELETE rules.
2. Anonymous, reader, and admin roles are tested separately.
3. Roles and authorities in tests match production rules.
4. Write tests include valid CSRF tokens when testing business permissions.
5. Missing-token and invalid-token tests are both rejected.
6. PUT, PATCH, and DELETE are tested alongside POST.
7. Preflight from allowed origins returns the right allow headers.
8. Preflight from disallowed origins receives no Allow-Origin.
9. Actual requests are tested separately with authorization and CSRF.
10. CORS credentials and wildcard origins are configured properly.
11. Response headers needed by the frontend are exposed.
12. JWT tests simulate exact authorities produced by production converters.
13. Rejected requests cause no database mutations or side effects.
14. Tests run with the application context's real Spring Security filter chain.

## Conclusion

Spring Security Test verifies that a Spring Data REST API protects resources according to user identity, permissions, and request state. `@WithMockUser`, `user()`, and `jwt()` support simulating authentication; `csrf()` verifies tokens for write operations; MockMvc `OPTIONS` with CORS headers verifies preflight and origin rules.

Test authentication, authorization, CSRF, and CORS as independent parts within the same request pipeline. A strong test suite proves both that valid requests succeed and that unauthorized requests, missing tokens, or untrusted origins are handled strictly according to the API contract.
