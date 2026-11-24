# Describing an API Is Different from Implementing API Behavior or Security

Springdoc-openapi generates an OpenAPI document from Spring Boot controllers, DTOs, and metadata. This document tells clients which endpoints exist, how parameters/bodies are accepted, what responses are returned, which schemas are used, and which authentication mechanisms are required. However, describing a rule is not the same as enforcing that rule.

An OpenAPI document can declare that an endpoint requires a Bearer JWT, a field cannot be blank, a 403 error response exists, or a page size limit applies. These declarations help clients and tools understand the contract. They do not verify JWT signatures, check user roles, reject empty strings, block unauthorized access, or limit request rates on their own. Those behaviors must be implemented and tested in Spring MVC, Bean Validation, Spring Security, filters/interceptors, services, or an API gateway.

This lesson clearly separates three layers:

1. **Contract description:** OpenAPI, Springdoc annotations, schemas, examples, security schemes, and responses.
2. **Application behavior:** request mapping, binding, validation, business rules, exception handling, and serialization.
3. **Security/operational policies:** authentication, authorization, CORS, CSRF, rate limiting, network policies, logging, and gateways.

The goal is to avoid situations where Swagger UI looks secure while the real endpoint remains open, or where documentation publishes a rule that the server does not enforce.

## 1. API Contract and Runtime Behavior Are Two Different Things

The API contract is the commitment observable from the client side. Runtime behavior is what the server actually does when receiving a request.

| Topic | Described in OpenAPI/Springdoc | Runtime Enforcement |
| --- | --- | --- |
| Endpoint | @Operation, @Parameter, Swagger @RequestBody, @ApiResponse, and mapping metadata read by Springdoc | @GetMapping, @PostMapping, Spring @RequestBody, controllers, handler mappings |
| Data types | @Schema, @ArraySchema, examples, required properties | Java types, Jackson, validation, converters |
| Required input | required in Parameter/Schema | @RequestParam(required = true), @NotNull, @NotBlank, @Valid |
| Authentication | @SecurityScheme, @SecurityRequirement | Spring Security filter chain, JWT decoder, session/authentication provider |
| Authorization | Security scopes/roles described on operations | requestMatcher, @PreAuthorize, authorization manager |
| CORS | Related details can be documented separately or via extensions | CorsConfigurationSource, Security CORS config, @CrossOrigin |
| CSRF | Protection mechanism/conditions described for clients | CsrfFilter and CsrfTokenRepository |
| Rate limits | Quotas can be described via description or extensions | Gateway, Bucket4j, Redis, filters, or dedicated services |
| Error responses | @ApiResponse describing status/schema/example | ResponseEntity, @ResponseStatus, @ExceptionHandler |
| Versioning | server URL, path/header parameters, deprecated metadata | Route mappings, version resolvers, compatibility logic |

For example: @SecurityRequirement(name = "bearerAuth") states that clients must send a Bearer token according to the defined security scheme. That annotation does not create a filter to check tokens. For the endpoint to reject missing or invalid tokens, the application must configure Spring Security.

## 2. Three Questions to Answer Before Publishing Documentation

For every rule appearing in Swagger UI, ask:

1. **What does the documentation say?** Can clients read that rule in the OpenAPI JSON/YAML?
2. **Where does the server enforce it?** Is there a controller, validator, security filter, service, or gateway actually applying the rule?
3. **Are there tests proving it?** Are requests violating the rule rejected with the expected status code and response body?

A rule is only considered complete when all three answers are clear. Never treat an OpenAPI annotation as a security control or validation mechanism.

## 3. @Operation Only Describes an Operation

@Operation sets summary, description, operationId, tags, and metadata for an endpoint:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    @Operation(
        operationId = "getOrderById",
        summary = "Get order by ID",
        description = """
            Returns order information that the current user is permitted to view.
            Endpoint requires Bearer JWT.
            """
    )
    public OrderResponse getById(@PathVariable UUID id) {
        return orderService.getVisibleOrder(id);
    }
}
~~~

@Operation does not on its own:

- Verify tokens.
- Check whether the caller has permission to view the order.
- Check whether the order belongs to the current tenant.
- Start a transaction or call a service.
- Change the response status code.

Those responsibilities belong in Spring Security, controllers/services, and other runtime components. Description is information for human readers; it is not an executable policy.

## 4. @Parameter Describes Parameters; It Does Not Replace Binding or Validation

Documentation example:

~~~java
@GetMapping
@Operation(summary = "Search orders")
public List<OrderResponse> search(
        @Parameter(
            description = "Order status",
            example = "PAID"
        )
        @RequestParam(required = false) String status) {
    return orderService.search(status);
}
~~~

@Parameter adds description/example for OpenAPI. @RequestParam is the annotation that participates in binding query parameters in Spring MVC.

If status may only accept a fixed set of values, use an enum or validator:

~~~java
public enum OrderStatus {
    PENDING, PAID, SHIPPED, CANCELLED
}

@GetMapping
public List<OrderResponse> search(
        @RequestParam(required = false) OrderStatus status) {
    return orderService.search(status);
}
~~~

When a client sends a value that cannot be converted to the enum, Spring MVC can return a binding error. If consistent error responses are needed, configure @RestControllerAdvice to standardize errors.

## 5. @Schema Describes Data; It Does Not Validate Data Itself

@Schema can provide type, format, description, example, allowable values, minimum, maximum, minLength, maxLength, pattern, and access mode:

~~~java
public record CreateCustomerRequest(
    @Schema(
        description = "Display name",
        example = "Nguyen An",
        minLength = 2,
        maxLength = 100
    )
    String displayName,

    @Schema(
        description = "Customer age",
        example = "28",
        minimum = "18",
        maximum = "120"
    )
    Integer age
) {}
~~~

The metadata above helps OpenAPI describe constraints. It does not guarantee Spring MVC will reject invalid requests. Add Bean Validation:

~~~java
public record CreateCustomerRequest(
    @NotBlank
    @Size(min = 2, max = 100)
    String displayName,

    @NotNull
    @Min(18)
    @Max(120)
    Integer age
) {}
~~~

And enable validation in the controller:

~~~java
@PostMapping
public ResponseEntity<CustomerResponse> create(
        @Valid @RequestBody CreateCustomerRequest request) {
    CustomerResponse created = customerService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

Both annotation groups play complementary roles:

- @Schema helps clients understand published constraints.
- @NotBlank, @Size, @Min, @Max, and @Valid participate in validating requests at runtime.

If you only declare minLength in @Schema without real validation, clients can send an empty string and the server will still accept it if the service does not check.

## 6. required in OpenAPI Differs from nullable and Validation

In OpenAPI, required usually describes whether a property or parameter must be present in the request. Nullable describes whether a null value is accepted. These are not the same concept.

Example:

~~~yaml
type: object
required:
  - displayName
properties:
  displayName:
    type: string
    minLength: 1
  nickname:
    type: string
    nullable: true
~~~

The nullable example above uses OpenAPI 3.0 syntax. In OpenAPI 3.1, null is represented using the corresponding JSON Schema type/union; check the document version your application publishes.

displayName must be present; nickname is optional and can be null according to the schema above. Runtime must have matching DTO, Jackson, and Bean Validation rules. Do not assume OpenAPI required automatically causes Spring MVC to return 400.

A few reminders:

- @NotNull checks that a value is not null.
- @NotBlank checks that a string is not null, not empty, and not whitespace-only.
- @NotEmpty checks that a string/collection/map is not empty, though a whitespace-only string can still pass.
- @Size checks size/length; it does not replace @NotNull.
- @Schema(requiredMode = REQUIRED) documents required in the spec; it does not replace runtime constraints.

## 7. @ApiResponse Describes Responses; It Does Not Emit Status Codes

Example:

~~~java
@GetMapping("/{id}")
@Operation(summary = "Get customer")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Customer found",
        content = @Content(
            schema = @Schema(implementation = CustomerResponse.class)
        )
    ),
    @ApiResponse(responseCode = "404", description = "Not found")
})
public CustomerResponse getById(@PathVariable UUID id) {
    return customerService.getById(id);
}
~~~

@ApiResponse responseCode = "404" only declares the 404 response in documentation. It does not make the method automatically return 404 when the ID does not exist.

Runtime can use a dedicated exception:

~~~java
public CustomerResponse getById(UUID id) {
    return repository.findById(id)
        .map(mapper::toResponse)
        .orElseThrow(() -> new CustomerNotFoundException(id));
}
~~~

And an exception handler:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(CustomerNotFoundException.class)
    ResponseEntity<ProblemDetail> handleNotFound(
            CustomerNotFoundException exception) {
        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        problem.setTitle("Customer not found");
        problem.setDetail("The requested customer was not found.");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }
}
~~~

Check both documentation and runtime to ensure the 404 response actually carries a body matching the published schema.

## 8. Distinguishing Authentication and Authorization

**Authentication** answers: who is sending the request? For example, verifying JWT signature, issuer, audience, expiration, or session.

**Authorization** answers: what actions is that identity permitted to perform on which resources? For example, only the order owner or staff with the right role may view an order.

OpenAPI security schemes usually describe how clients supply authentication credentials. Business-level authorization must still be enforced on the server.

| Situation | Typical Outcome |
| --- | --- |
| Missing credentials on an endpoint requiring login | 401 Unauthorized |
| Invalid or expired token/session | 401 Unauthorized |
| Authenticated but insufficient permissions | 403 Forbidden |
| Permitted to access, yet resource does not exist | 404 Not Found |

Do not use 404 as an arbitrary substitute for authorization. Some systems intentionally hide resource existence using 404; if choosing that policy, apply it consistently and document the contract accurately.

## 9. Declaring Bearer JWT in OpenAPI

Springdoc can describe an HTTP Bearer scheme using @SecurityScheme:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    security = @SecurityRequirement(name = "bearerAuth")
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT",
    description = "JWT access token in the Authorization header"
)
public class OpenApiSecurityConfiguration {
}
~~~

OpenAPI can then generate a security scheme similar to:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
security:
  - bearerAuth: []
~~~

Swagger UI will display the Authorize mechanism for users to enter tokens. This is a client experience and contract metadata; it does not verify tokens on the server's behalf.

## 10. Attaching Security Requirements at the Operation Level

If security is not declared globally, requirements can be attached to a controller or operation:

~~~java
@RestController
@RequestMapping("/api/profile")
@SecurityRequirement(name = "bearerAuth")
public class ProfileController {

    @GetMapping
    @Operation(summary = "View current profile")
    public ProfileResponse me() {
        return profileService.currentProfile();
    }
}
~~~

A security requirement in OpenAPI tells clients to use the scheme named bearerAuth. This name must match the key declared in components.securitySchemes.

If names mismatch, the document can contain invalid references or Swagger UI will fail to display the authentication mechanism properly.

## 11. Public Endpoints When the Document Has Global Security

If OpenAPI declares a global security requirement, public endpoints must be documented as requiring no security:

~~~java
@GetMapping("/health")
@Operation(
    summary = "Check service status",
    security = {}
)
public HealthResponse health() {
    return healthService.currentStatus();
}
~~~

In OpenAPI, an empty security array on an operation overrides the global requirement. This only affects the contract description.

Runtime must still configure the corresponding endpoint as permitAll if that is the intended policy. Conversely, if documentation marks an endpoint public while Spring Security demands a token, Swagger UI will mislead clients.

## 12. Implementing a JWT Resource Server with Spring Security

Example runtime configuration for an API accepting Bearer JWT:

~~~java
@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/v3/api-docs/**",
                    "/swagger-ui/**",
                    "/swagger-ui.html"
                ).permitAll()
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

The example above illustrates a filter chain, not a copy-paste configuration for every system. You must decide:

- Whether the API uses stateless JWT or sessions/cookies.
- Whether CSRF needs to be enabled.
- Whether Swagger docs are public or require login.
- Which endpoints are permitAll, authenticated, or require roles.
- Where JWT issuer, audience, key rotation, and claim mapping are configured.

When using a JWT resource server, the application also needs appropriate dependencies and decoder/issuer configuration, such as spring.security.oauth2.resourceserver.jwt.issuer-uri. Without a valid issuer/decoder, declaring @SecurityScheme in OpenAPI will not make JWT work.

## 13. Method-Level Authorization with @PreAuthorize

Business actions can be protected with method security:

~~~java
@Service
public class OrderService {

    @PreAuthorize("hasRole('ADMIN') or @orderAccess.canRead(#id, authentication)")
    public OrderResponse getVisibleOrder(UUID id) {
        return repository.findById(id)
            .map(mapper::toResponse)
            .orElseThrow(() -> new OrderNotFoundException(id));
    }
}
~~~

@PreAuthorize is a runtime mechanism once method security is enabled via @EnableMethodSecurity. The expression checks roles or an authorization bean before the method executes.

Comparison:

- @SecurityRequirement describes the authentication scheme in OpenAPI.
- authenticated() in SecurityFilterChain requires the request to be authenticated.
- hasRole('ADMIN') or @PreAuthorize checks runtime permissions.
- OAuth2 scopes in OpenAPI describe scopes clients need; the server must still check the corresponding authorities/scopes.

Never let a controller return data by a client-supplied ID without verifying access permissions for that specific resource. Successful authentication does not mean the user may view every orderId.

## 14. OAuth2 Scopes in Docs vs. Runtime Authority Checks

OpenAPI can describe OAuth2 authorization flows and scopes:

~~~java
@SecurityScheme(
    name = "oauth2",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://identity.example.com/oauth/authorize",
            tokenUrl = "https://identity.example.com/oauth/token",
            scopes = {
                @OAuthScope(name = "orders:read", description = "Read orders"),
                @OAuthScope(name = "orders:write", description = "Create or modify orders")
            }
        )
    )
)
~~~

Operations can declare scopes:

~~~java
@Operation(
    summary = "Read order",
    security = @SecurityRequirement(
        name = "oauth2",
        scopes = {"orders:read"}
    )
)
~~~

This is the contract for clients. Runtime must map claims/scopes in the token to GrantedAuthority and enforce permissions, for example:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
public OrderResponse getOrder(UUID id) {
    return orderService.load(id);
}
~~~

If OpenAPI declares orders:read while the server does not check the authority, the documentation promises a policy runtime does not enforce. Conversely, if the server requires a scope without documentation stating it, clients will struggle to integrate.

## 15. API Keys Are Not Verified Automatically by @SecurityScheme

OpenAPI can describe an API key:

~~~java
@SecurityScheme(
    name = "partnerApiKey",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-Partner-Key",
    description = "API key issued by partner system"
)
~~~

This tells Swagger UI to send the X-Partner-Key header. The server must still have a filter or authentication provider that verifies:

- Whether the header is present.
- Whether the key is valid, active, and unrevoked.
- Which partner owns the key.
- Whether that partner is allowed to call the operation.
- Whether the partner's quota remains or has been exceeded.

Never put real API keys in examples, source code, configuration files committed to Git, or public OpenAPI documents.

## 16. Hiding Swagger UI Does Not Protect Endpoints

Documentation-hiding annotations and settings only affect visibility:

- @Hidden or @Operation(hidden = true) can exclude operations from OpenAPI.
- GroupedOpenApi can restrict paths included in a group.
- Swagger UI can be disabled or left unexposed.
- /v3/api-docs can be secured separately.

None of these replace authorization for business endpoints.

For example, hiding /api/admin/** from Swagger UI while SecurityFilterChain still sets permitAll leaves the endpoint directly callable via curl or any HTTP client.

Conversely, keeping documentation public does not mean business endpoints must be public. You can allow reading the OpenAPI document while protecting all operations with Spring Security. Distinguish permission to read documentation from permission to call the API.

## 17. CORS Is a Browser Runtime Policy, Not Authentication

CORS (Cross-Origin Resource Sharing) governs whether a browser allows JavaScript from one origin to read responses from another origin. CORS does not authenticate users and does not replace authorization.

Configuring CORS in Spring:

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration configuration = new CorsConfiguration();
    configuration.setAllowedOrigins(List.of("https://app.example.com"));
    configuration.setAllowedMethods(
        List.of("GET", "POST", "PUT", "PATCH", "DELETE")
    );
    configuration.setAllowedHeaders(
        List.of("Authorization", "Content-Type", "X-Request-Id")
    );
    configuration.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", configuration);
    return source;
}
~~~

Enable CORS in the filter chain:

~~~java
http.cors(Customizer.withDefaults());
~~~

When using credentials, do not set allowedOrigins to wildcard *. Restrict to trusted origins. CORS is primarily a browser control; non-browser HTTP clients can still call endpoints, so the backend must still authenticate and authorize requests.

## 18. CSRF Depends on How Credentials Are Stored

CSRF (Cross-Site Request Forgery) is especially important when browsers automatically send credentials such as session cookies. If an application uses cookies/sessions, evaluate CSRF tokens and configure them appropriately.

For APIs using Bearer tokens sent explicitly in the Authorization header rather than relying on automatic cookies, the CSRF threat model differs. However, do not disable CSRF merely because URLs start with /api.

The decision to enable/disable CSRF should be based on:

- Whether credentials are sent automatically by browsers.
- Whether session cookies are used.
- Whether any endpoints use form login or cookie authentication.
- Whether the frontend sends tokens in headers or cookies.
- Cookie SameSite, Secure, and HttpOnly settings.

OpenAPI can describe headers/tokens clients must send, yet does not implement CSRF protection itself.

## 19. Rate Limiting and Quotas Are Not Enforced by OpenAPI

An operation description might state:

~~~java
@Operation(
    summary = "Send OTP",
    description = """
        Maximum 3 sends within 10 minutes per phone number.
        When quota is exceeded, the API returns HTTP 429.
        """
)
@ApiResponse(responseCode = "429", description = "Request limit exceeded")
~~~

The metadata above does not count requests or block users. Runtime must implement a rate-limiting mechanism in a gateway, filter, or service.

Common algorithm examples:

- Fixed window: counts requests within fixed time windows.
- Sliding window: computes quota over a sliding window.
- Token bucket: tokens refill at a rate; requests consume tokens.
- Leaky bucket: processes traffic at a steady rate.

Rate limits should be keyed by an appropriate policy: IP, user, API key, tenant, endpoint, or a combination. In multi-instance systems, counters must be shared via Redis or equivalent infrastructure; local memory on a single instance cannot enforce cluster-wide quotas.

When limits are exceeded, runtime typically returns 429 and may include Retry-After or quota headers. If publishing these headers, document them in OpenAPI and verify they actually appear in responses.

## 20. Security Schemes, Server Policies, and Gateway Policies

Not every security policy belongs to the same layer:

| Policy | Layer Typically Responsible |
| --- | --- |
| JWT signature, issuer, expiration | Resource server / authentication provider |
| Role, scope, ownership, tenant | Spring Security method authorization / service |
| TLS termination, IP allowlist | Load balancer, ingress, or API gateway |
| WAF, bot protection | WAF/gateway |
| Rate limits, quotas by API key | Gateway or distributed limiter |
| CORS | Browser policy configured at gateway or application |
| Audit logging | Application security/audit layer |
| OpenAPI security scheme | Contract describing how clients authenticate |

A request may pass through multiple layers. For example, a gateway checks API keys and rate limits, Spring Security checks JWTs, and the service checks order ownership. OpenAPI needs to describe what clients must do, yet cannot replace configuration at any runtime layer.

## 21. Documenting 401 and 403 Responses

Error responses can be declared on an operation:

~~~java
@ApiResponses({
    @ApiResponse(responseCode = "200", description = "Success"),
    @ApiResponse(
        responseCode = "401",
        description = "Missing or invalid authentication credentials",
        content = @Content(
            schema = @Schema(implementation = ProblemDetail.class)
        )
    ),
    @ApiResponse(
        responseCode = "403",
        description = "Authenticated but lacks sufficient permissions",
        content = @Content(
            schema = @Schema(implementation = ProblemDetail.class)
        )
    )
})
~~~

For runtime to actually return the right statuses:

- AuthenticationEntryPoint handles unauthenticated requests or invalid credentials.
- AccessDeniedHandler handles authenticated requests that are not permitted.
- Application exception handlers handle business errors such as resource not found.

Do not assume @RestControllerAdvice catches every error from the Spring Security filter chain. Many security errors occur before requests reach controllers, so configure matching handlers in HttpSecurity.

## 22. Separating Security Error Responses from Business Error Responses

Public error schemas can be unified using ProblemDetail or a dedicated DTO. However, determine which layer produces each error:

| Error | Where It Typically Originates | Handling Mechanism |
| --- | --- | --- |
| Missing/invalid JWT | Security filter chain | AuthenticationEntryPoint |
| Logged in yet lacks permission | Authorization filter/method security | AccessDeniedHandler |
| Invalid request body | Spring MVC/Bean Validation | MethodArgumentNotValidException handler |
| Unparseable parameter | Spring MVC binding | TypeMismatch/MethodArgumentTypeMismatch handler |
| Resource not found | Controller/service | Exception handler |
| Quota exceeded | Gateway/filter | Rate-limit response handler |

If layers return different body shapes, OpenAPI should describe each response accurately or standardize runtime first. Never publish a single ErrorResponse if 401, 403, 400, and 429 actually have different structures.

## 23. API Versioning and Deprecation

OpenAPI can describe versions via server URLs, paths, header parameters, or metadata. Example:

~~~java
@Operation(
    summary = "Get profile",
    deprecated = true,
    description = "Legacy endpoint; use /api/v2/profile instead."
)
~~~

deprecated = true marks an operation as no longer recommended. It does not disable the endpoint or automatically route requests to the new version.

Runtime must keep the legacy route during the compatibility window, run version resolvers, or return errors per the published sunset policy. Removing a mapping is a runtime change; marking deprecated is contract metadata.

## 24. Distinguishing @Hidden from Access Protection

Example:

~~~java
@Hidden
@RestController
@RequestMapping("/internal/diagnostics")
public class DiagnosticsController {

    @GetMapping
    public DiagnosticsResponse inspect() {
        return diagnosticsService.inspect();
    }
}
~~~

@Hidden can exclude the controller from documentation. Yet if SecurityFilterChain does not block /internal/diagnostics, users can still call the URL directly.

Combine it with a runtime policy:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/internal/diagnostics/**").hasRole("OPS")
    .anyRequest().authenticated()
);
~~~

Never use hiding documentation as a way to protect secrets. Security through obscurity does not replace authentication, authorization, network isolation, or auditing.

## 25. Documentation Tests and Runtime Tests Are Two Separate Suites

An integration test fetching /v3/api-docs can check security schemes and response metadata:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiSecurityDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void documentsBearerAuthentication() throws Exception {
        String json = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode spec = objectMapper.readTree(json);

        assertThat(
            spec.at("/components/securitySchemes/bearerAuth/scheme").asText()
        ).isEqualTo("bearer");
    }
}
~~~

This test only proves the documentation declares the Bearer scheme. It does not prove tokens are verified.

## 26. Runtime Testing: Missing Tokens Must Be Rejected

For endpoints requiring authentication:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsAnonymousRequest() throws Exception {
        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

The result depends on the real SecurityFilterChain and test configuration. If tests use a mock user or disable filters, they do not prove anonymous requests are blocked.

## 27. Runtime Testing: Authenticated Users Without Sufficient Permissions

For method security or request authorization:

~~~java
@Test
@WithMockUser(roles = "CUSTOMER")
void deniesCustomerFromAdminEndpoint() throws Exception {
    mockMvc.perform(get("/api/admin/reports"))
        .andExpect(status().isForbidden());
}

@Test
@WithMockUser(roles = "ADMIN")
void allowsAdminToReadAdminEndpoint() throws Exception {
    mockMvc.perform(get("/api/admin/reports"))
        .andExpect(status().isOk());
}
~~~

These tests verify runtime authorization with a simulated security context. If the application uses custom JWT claim mappings, add JWT converter or resource server tests using test tokens with matching claims/scopes.

## 28. Runtime Validation Testing

Having minLength in the OpenAPI schema is not enough. Test violating requests:

~~~java
@Test
void rejectsBlankDisplayName() throws Exception {
    mockMvc.perform(post("/api/customers")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "displayName": "   ",
                  "age": 28
                }
                """))
        .andExpect(status().isBadRequest());
}
~~~

This test requires the controller to use @Valid and the DTO to have @NotBlank. If response bodies follow ProblemDetail, also assert title, status, and field errors per the published contract.

## 29. Testing 401/403 and Synchronized Response Schemas

Security documentation and runtime must be tested in parallel:

~~~java
@Test
void documentsUnauthorizedAndForbiddenResponses() throws Exception {
    JsonNode spec = loadOpenApi();
    JsonNode responses = spec.at(
        "/paths/~1api~1orders/get/responses"
    );

    assertThat(responses.has("401")).isTrue();
    assertThat(responses.has("403")).isTrue();
}
~~~

And runtime testing:

~~~java
@Test
void anonymousAndForbiddenRequestsHaveExpectedStatuses() throws Exception {
    mockMvc.perform(get("/api/orders"))
        .andExpect(status().isUnauthorized());

    mockMvc.perform(get("/api/admin/reports")
            .with(user("customer").roles("CUSTOMER")))
        .andExpect(status().isForbidden());
}
~~~

The examples above assume the test has a loadOpenApi() helper, the Spring Security test dependency, and the corresponding filter chain. Adjust endpoints/JSON Pointer paths to match your actual document.

## 30. Swagger UI Authorize Is Not Proof an Endpoint Is Protected

When clicking Authorize and entering a token in Swagger UI:

1. The UI stores the token according to its session mechanism.
2. The UI adds the Authorization header to requests matching the security requirement.
3. The server receives the request.
4. Spring Security or the gateway verifies the credential.
5. The authorization layer decides whether the user is allowed to perform the action.

If step 4 or 5 does not exist, the UI can still show an Authorize button while the server remains unprotected. Conversely, if the server protects the endpoint yet the docs omit the scheme, clients may not know how to send tokens.

Never include real tokens or secrets in Swagger UI screenshots, logs, examples, or shared documentation.

## 31. Configuring Protection for Swagger UI and OpenAPI Endpoints

Depending on organizational policy, API documentation can be public, internal-only, or require authentication. This is a separate runtime decision.

Example securing docs:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/v3/api-docs/**", "/swagger-ui/**")
        .hasRole("DEVELOPER")
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().authenticated()
);
~~~

If docs require login, users need a suitable access path. With OAuth2, you can configure Swagger UI OAuth redirect/client settings; never embed client secrets in a public frontend.

If docs are public, review carefully:

- Were any internal endpoints accidentally placed into the public group?
- Do schemas/examples expose internal data or sample tokens?
- Do server URLs mistakenly point to development environments?
- Do administrative endpoints need to be split into a separate group or hidden from public docs?

Restricting documentation reduces information leakage, yet runtime endpoints must still be protected.

## 32. GroupedOpenApi Only Splits Documentation; It Does Not Split Access Control

Example creating public and internal groups:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/public/**")
        .build();
}

@Bean
GroupedOpenApi internalApi() {
    return GroupedOpenApi.builder()
        .group("internal")
        .pathsToMatch("/api/internal/**")
        .build();
}
~~~

Groups control which operations are included in a document. They do not create separate SecurityFilterChains and do not automatically protect /api/internal/**.

To restrict access to internal APIs, configure request matchers, roles/scopes, network policies, or a gateway. To restrict who can read the internal OpenAPI document, protect the corresponding group URL with runtime security.

## 33. Easily Misunderstood Annotation Examples

| Annotation/Config | Primary Effect | What It Does Not Do |
| --- | --- | --- |
| @Operation | Describes an operation | Does not handle requests |
| @Parameter | Describes a parameter | Does not bind queries |
| @Schema | Describes a schema | Does not validate bodies |
| @ApiResponse | Describes a response | Does not emit status codes |
| @SecurityScheme | Declares authentication mechanism | Does not verify tokens |
| @SecurityRequirement | Attaches security requirement to operation | Does not grant permissions |
| @Hidden | Hides from OpenAPI | Does not block URLs |
| @Deprecated or deprecated metadata | Signals legacy API | Does not disable endpoints |
| @Valid | Triggers validation at supported points | Does not replace all business rules |
| @PreAuthorize | Checks permissions when method is called | Does not replace credential authentication in filter chain |
| @CrossOrigin | Configures CORS for mapping | Not authentication |
| @GetMapping | Registers GET route | Does not require login on its own |

Some annotations belong to Spring runtime, while others belong to Swagger/OpenAPI. Check packages/imports to avoid confusion.

## 34. Common Errors When Documentation and Runtime Are Out of Sync

| Symptom | Cause | Fix |
| --- | --- | --- |
| Swagger UI has Authorize yet requests pass without token | Only @SecurityScheme/@SecurityRequirement declared | Configure Spring Security authentication |
| Docs say endpoint is public yet server returns 401 | Wrong security requirement or public description | Align OpenAPI with permitAll/authentication policy |
| Docs list 403 yet runtime returns 200 | Only @ApiResponse declared | Enforce authorization and write security tests |
| Schema has minLength yet server accepts empty string | Only @Schema present | Use Bean Validation and @Valid |
| Docs list 429 yet no rate limiting exists | Only @ApiResponse added | Configure limiter in gateway/filter and test quotas |
| Endpoint marked @Hidden yet curl still succeeds | Hiding docs does not block routes | Configure runtime authorization |
| CORS fails despite valid token | Origin/header/method not allowed | Configure CORS; do not weaken authentication |
| Browser succeeds yet other clients rejected | Differences in credentials/CORS/proxy | Analyze actual requests and per-layer policies |
| 401 and 403 have different body schemas | Security handlers not unified | Configure AuthenticationEntryPoint/AccessDeniedHandler |
| Swagger docs unreachable after enabling security | Docs URLs not permitted or user lacks role | Decide public/internal docs policy and configure accordingly |
| Internal group endpoints still reachable via direct URL | GroupedOpenApi only filters documents | Protect routes via security matchers/gateway |
| Legacy endpoint still runs despite deprecated | Deprecated is metadata only | Implement runtime lifecycle/version policy |

## 35. Workflow for Reviewing an API Before Publishing

For each operation:

1. Identify the audience: public, partner, internal, or admin.
2. Document request/response contracts using OpenAPI.
3. Determine required authentication schemes and scopes/roles.
4. Configure Spring Security or a gateway to enforce policies.
5. Add runtime validation for requests.
6. Check ownership/tenant permissions in services, not only based on client-sent IDs.
7. Standardize 400, 401, 403, 404, 409, 422, and 429 if the endpoint can return them.
8. Verify CORS, CSRF, and rate limits according to how credentials are used.
9. Write OpenAPI tests to verify the contract.
10. Write runtime tests for anonymous, authenticated, forbidden, and invalid requests.
11. Verify gateway/ingress policies in the deployment environment.
12. Compare the document against actual behavior before publishing.

## 36. Completion Checklist

- [ ] Every operation has clear summary, description, and parameters.
- [ ] @Schema accurately describes types, formats, examples, and data bounds.
- [ ] Critical constraints have runtime Bean Validation or business validation.
- [ ] @ApiResponse matches actual status codes.
- [ ] Security scheme names match security requirements consistently.
- [ ] Public endpoints are documented as public and intentionally configured permitAll at runtime.
- [ ] Protected endpoints document security and require credentials at runtime.
- [ ] Roles/scopes/ownership are enforced at runtime.
- [ ] @Hidden and GroupedOpenApi are not treated as URL protection measures.
- [ ] CORS is configured for necessary origins; no arbitrary wildcards with credentials.
- [ ] CSRF is evaluated according to how credentials are stored and sent.
- [ ] Rate limiting actually operates if docs advertise quotas/429.
- [ ] Security handlers return 401/403 matching the schema.
- [ ] Swagger UI and /v3/api-docs are protected per chosen policy.
- [ ] OpenAPI contract tests and runtime security/validation tests exist.
- [ ] Gateway, ingress, and application policies do not contradict each other.
- [ ] No real secrets or tokens appear in docs/examples.

## 37. Conclusion

Springdoc-openapi helps publish API contracts in a structured way: endpoints, parameters, schemas, responses, and authentication mechanisms clients must use. Yet an OpenAPI document is a description, not a policy enforcement engine. @SecurityRequirement does not verify JWTs; @Schema does not validate requests; @ApiResponse does not generate status codes; @Hidden does not block endpoints; GroupedOpenApi does not create access permissions.

A reliable API requires aligning three parts: documentation that describes accurately, an application that enforces properly, and tests that prove both. Use Springdoc to communicate contracts to clients, Spring MVC/Bean Validation to handle requests, Spring Security for authentication/authorization, gateways/filters for operational policies, and test runtime behavior independently of OpenAPI checks. That avoids the false sense of security from having clean Swagger docs over unprotected endpoints.

## References

- [Springdoc OpenAPI — Documentation and FAQ](https://springdoc.org/)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [OpenAPI Specification — Security Requirement Object](https://spec.openapis.org/oas/latest.html#security-requirement-object)
