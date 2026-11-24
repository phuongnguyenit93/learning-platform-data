# Declared Security Does Not Automatically Create a SecurityFilterChain or Validate Tokens

When documenting an API with springdoc-openapi, you can declare bearer tokens, API keys, Basic Authentication, or OAuth2 so Swagger UI displays an Authorize button and client generators know how to send credentials. However, these declarations only describe the **security contract** in OpenAPI. They do not create security filters, verify JWT signatures, validate API keys, or decide whether a user has permission to call an endpoint.

In Spring Boot, actual request protection is handled by Spring Security via **SecurityFilterChain**, authentication providers, resource servers, and authorization rules. Both parts must be configured consistently: OpenAPI tells clients which credentials to send; the backend actually verifies those credentials and enforces corresponding permissions.

## 1. Two security layers to distinguish

An API has two related yet independent security layers:

1. **Security description in OpenAPI:** states which authentication mechanism an operation requires and where clients must send credentials.
2. **Runtime request protection:** verifies identity, checks permissions, applies CSRF/CORS, and decides whether to allow or reject a request.

For example, OpenAPI may declare bearer JWT:

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

This configuration tells Swagger UI that requests need the header:

~~~http
Authorization: Bearer <access-token>
~~~

Yet if the application lacks an appropriate SecurityFilterChain or resource server, the server may still accept requests without a token. Conversely, the backend may require tokens while the OpenAPI document declares no security scheme; in that case, clients reading the documentation will not know how to authenticate.

Both the documentation and actual runtime behavior must be tested; do not use one as proof of the other.

## 2. @SecurityScheme defines the mechanism in documentation

The @SecurityScheme annotation from swagger-annotations registers a security scheme in components.securitySchemes.

Bearer JWT example:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT",
    description = "JWT access token"
)
@Configuration
class OpenApiSecurityConfiguration {
}
~~~

Corresponding OpenAPI output:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: JWT access token
~~~

Significant attributes:

- name: scheme key in components.securitySchemes.
- type: authentication type such as http, apiKey, oauth2, or openIdConnect.
- scheme: HTTP authentication scheme name, such as bearer or basic.
- bearerFormat: token format hint; the value JWT is only metadata.
- in and paramName: parameter location and name when using an API key.
- flows or openIdConnectUrl: additional information for OAuth2/OpenID Connect.

Registering a scheme does not create a Spring Security filter. Nor does bearerFormat = JWT cause the application to parse or verify JWTs automatically.

## 3. @SecurityRequirement attaches a scheme to operations

A registered scheme must be attached to an operation or the entire document using a security requirement. Example:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/me")
@Operation(
    summary = "Get current user's profile",
    security = @SecurityRequirement(name = "bearerAuth")
)
public ProfileResponse getCurrentProfile() {
    return profileService.currentProfile();
}
~~~

The name bearerAuth in @SecurityRequirement must match the key declared in @SecurityScheme exactly.

OpenAPI output can contain:

~~~yaml
paths:
  /api/me:
    get:
      security:
        - bearerAuth: []
~~~

You can place a security requirement at the document level using @OpenAPIDefinition:

~~~java
@OpenAPIDefinition(
    security = @SecurityRequirement(name = "bearerAuth")
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
@Configuration
class OpenApiSecurityConfiguration {
}
~~~

When security is declared at the root level, operations typically inherit that requirement unless they have their own security. Inspect the generated JSON to verify which operations are actually marked protected.

@SecurityRequirement only states that clients must use the registered scheme. It does not validate tokens and does not replace authorizeHttpRequests in Spring Security.

## 4. Understanding security requirements in OpenAPI

OpenAPI represents security requirements as a list. Each element in the list is a satisfiable option; schemes within the same element must be satisfied simultaneously.

Example requiring only a bearer token:

~~~yaml
security:
  - bearerAuth: []
~~~

If an operation accepts either of two authentication methods, it can be expressed as two options:

~~~yaml
security:
  - bearerAuth: []
  - apiKeyAuth: []
~~~

If both a bearer token and an API key are required at the same time, place them in the same element:

~~~yaml
security:
  - bearerAuth: []
    apiKeyAuth: []
~~~

An operation can be public even if the document sets security at the root level. In OpenAPI, security: [] on an operation indicates that the operation requires no security; a requirement with an empty object {} indicates an anonymous access option alongside an authenticated option:

~~~yaml
paths:
  /api/catalog:
    get:
      security: []
      summary: Public listing
      responses:
        '200':
          description: Success
  /api/profile:
    get:
      security:
        - bearerAuth: []
        - {}
~~~

Do not confuse security: [] with omitting the security field. If an operation does not declare its own security, it can inherit the root-level requirement.

## 5. SecurityFilterChain is what protects real requests

In Spring Security, SecurityFilterChain defines which requests pass through which filters, how authentication is required, and which resources may be accessed.

Example stateless API configuration using bearer JWT with Spring Boot 3 and Spring Security 6:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    "/v3/api-docs/**",
                    "/swagger-ui/**",
                    "/swagger-ui.html"
                ).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/catalog/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

The configuration above performs distinct tasks:

- csrf: defines the CSRF protection policy.
- sessionManagement: avoids storing authentication sessions for a stateless API.
- authorizeHttpRequests: decides which requests are public, require scopes, or require login.
- oauth2ResourceServer().jwt(...): enables bearer JWT verification.
- SecurityFilterChain: registers the filter chain that actually processes requests.

The example allowing public access to /v3/api-docs/** and /swagger-ui/** is only suitable when the organization intends to publish the documentation. If documentation is internal or contains non-public information, protect these paths under a separate policy.

Only disable CSRF when the authentication model truly fits, such as stateless APIs using bearer tokens in the Authorization header and not relying on cookies sent automatically by browsers. If using session cookies or cookie authentication, evaluate and retain an appropriate CSRF mechanism.

## 6. Configuring a JWT Resource Server

For Spring Security to verify JWTs, the project needs the resource server dependency. With Maven and Spring Boot dependency management:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

You can configure the issuer URI:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/shop
~~~

Spring Security uses the issuer's metadata to locate public keys and configure the decoder. Upon receiving a bearer token, the resource server verifies the signature and configured time/issuer claims. Expired tokens, invalid signatures, or mismatched issuers will be rejected.

If the API requires audience validation, configure an appropriate additional validator. Do not assume that merely setting issuer-uri automatically satisfies every system-specific rule.

In OpenAPI, the bearer scheme only describes how clients send tokens. It does not specify an issuer URI for Spring to auto-configure, generate JWTs, or decide which claims are trusted.

## 7. Distinguishing authentication and authorization

Two steps are frequently confused:

- **Authentication:** determines who the caller is and whether credentials are valid.
- **Authorization:** determines whether the caller is permitted to perform that action or access that resource.

Examples:

- No token sent: request can be rejected with 401.
- Expired or mis-signed token sent: authentication fails, typically returning 401.
- Valid token lacking orders.write scope: authentication succeeds but permissions are insufficient, typically returning 403.
- Token with matching scope: request can proceed to the controller, though the service must still check ownership or business rules if needed.

Simply having a token does not grant permission to call every endpoint. OpenAPI security requirements describe credentials; authorization policies must be implemented in SecurityFilterChain or the business layer.

## 8. Mapping scopes and authorities

With OAuth2 JWTs, Spring Security typically maps scope/scp claims into authorities prefixed with SCOPE_.

Example token with scopes:

~~~json
{
  "sub": "user-123",
  "scope": "orders.read orders.write"
}
~~~

You can check authorities in HTTP configuration:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .anyRequest().authenticated()
)
~~~

Or protect service methods:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class OrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderResponse findById(String id) {
        // Find and return the order.
        return repository.findResponseById(id);
    }
}
~~~

To use @PreAuthorize, enable method security:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Inspect the actual claims from your identity provider. Some systems use roles, groups, or custom claims instead of scope; in that case, configure a converter to map them to GrantedAuthority. Do not rename authorities in OpenAPI expecting Spring Security to understand claims automatically.

## 9. Declaring an API key in OpenAPI

API keys are usually sent via header, query parameter, or cookie. Example of an API key via header:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeIn;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "apiKeyAuth",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-API-Key",
    description = "API key issued by the system"
)
@Configuration
class ApiKeyOpenApiConfiguration {
}
~~~

Corresponding OpenAPI:

~~~yaml
components:
  securitySchemes:
    apiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
~~~

Attach the scheme to an operation:

~~~java
@Operation(
    summary = "Look up partner data",
    security = @SecurityRequirement(name = "apiKeyAuth")
)
@GetMapping("/api/partner/data")
public PartnerDataResponse getPartnerData() {
    return partnerService.loadData();
}
~~~

This declaration lets Swagger UI display an API key field and send the X-API-Key header. The backend still needs a filter, authentication provider, or equivalent mechanism to read and verify the key, and check its status, expiration, scope, and permissions.

Do not store plaintext API keys in source code or logs. Support issuing new keys, revoking, and rotating keys; restrict permissions per key and transmit over HTTPS. Avoid placing keys in query strings because URLs frequently appear in logs, browser history, and monitoring systems.

## 10. Basic Authentication also requires runtime configuration

OpenAPI can describe HTTP Basic:

~~~java
@SecurityScheme(
    name = "basicAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "basic",
    description = "HTTP Basic Authentication"
)
@Configuration
class BasicAuthOpenApiConfiguration {
}
~~~

Operation using the scheme:

~~~java
@Operation(
    summary = "View admin report",
    security = @SecurityRequirement(name = "basicAuth")
)
@GetMapping("/api/admin/report")
public ReportResponse getReport() {
    return reportService.getReport();
}
~~~

To authenticate Basic at runtime, Spring Security needs httpBasic, a UserDetailsService, or an appropriate authentication provider configured:

~~~java
@Bean
SecurityFilterChain basicSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());

    return http.build();
}
~~~

This configuration is a minimal example. In a real application, configure user stores, password hashing, authorization, HTTPS, and brute-force protection policies. Basic Authentication only encodes credentials in Base64 in the header, not payload encryption; never use it over unprotected HTTP connections.

## 11. OAuth2 and OpenID Connect

OpenAPI can describe OAuth2 flows or OpenID Connect so clients know how to obtain and send tokens. For example, an OAuth2 scheme can declare an authorization code flow with an authorization URL, token URL, and scopes.

~~~yaml
components:
  securitySchemes:
    shopOAuth:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://identity.example.com/oauth2/authorize
          tokenUrl: https://identity.example.com/oauth2/token
          scopes:
            orders.read: Read orders
            orders.write: Create or update orders
~~~

Operation requiring a scope:

~~~yaml
security:
  - shopOAuth:
      - orders.read
~~~

Defining flows in OpenAPI informs tools about endpoints and scopes. It does not turn Spring Boot into an authorization server, auto-register clients, or issue tokens. The backend resource server must still validate access tokens against issuer, signature, lifetime, audience, and permission rules.

OpenID Connect is an identity layer built on OAuth2. When using openIdConnect, OpenAPI references the discovery URL; the authentication system and resource server must still be configured independently.

## 12. Global security schemes and public operations

If every endpoint requires a bearer token, you can declare the security requirement at the root level. Yet many APIs have both public and protected endpoints.

Document example:

~~~yaml
security:
  - bearerAuth: []

paths:
  /api/catalog:
    get:
      security: []
      summary: Public catalog
      responses:
        '200':
          description: Success

  /api/me:
    get:
      summary: Current profile
      responses:
        '200':
          description: Success
~~~

/api/catalog is public in the OpenAPI contract because the operation has security: []; /api/me inherits the bearer requirement from the root.

It must stay synchronized with the backend. If OpenAPI marks an endpoint public while SecurityFilterChain requires authentication, clients will send requests without tokens and receive 401. If documentation requires bearer while the backend allows anonymous access, the documentation will confuse clients.

A public endpoint in the documentation can still have rate limits or other access conditions; security requirements only describe authentication mechanisms per OpenAPI.

## 13. Protecting Swagger UI and OpenAPI JSON

Swagger UI and /v3/api-docs/** paths are often left public in development examples for lookup convenience. In internal environments, the documentation may reveal:

- Endpoint names and system structure.
- Request/response schemas.
- Business workflows and error codes.
- Headers or security schemes.
- Admin or partner-integration endpoints.

Decide separately:

1. Who may open the Swagger UI interface?
2. Who may download the OpenAPI JSON/YAML?
3. Who may call the actual API?
4. With which credentials does Swagger UI call the API?

If /v3/api-docs/** is protected, Swagger UI must also have a way to access the document. If the UI requires login yet the spec file is blocked before the UI can load it, the page may fail to display operations. You can use the same login mechanism, a reverse proxy, or distribute the spec via an appropriate internal channel.

Do not publish documentation publicly merely because Try it out has been disabled. supportedSubmitMethods only limits sending requests from the UI; it does not hide documentation or protect endpoints.

## 14. 401 and 403 must be handled properly

In Spring Security:

- **401 Unauthorized:** the caller is unauthenticated or credentials are invalid.
- **403 Forbidden:** the caller is authenticated but lacks sufficient permissions.

The name Unauthorized for status 401 can be misleading; semantically, it is an authentication error. 403 typically denotes authorization denied.

You can configure handlers to return consistent JSON errors:

- AuthenticationEntryPoint handles authentication failures.
- AccessDeniedHandler handles authorization failures.

Illustrative example:

~~~java
http.exceptionHandling(exceptions -> exceptions
    .authenticationEntryPoint((request, response, exception) -> {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.getWriter().write(
            "{\"code\":\"UNAUTHENTICATED\",\"message\":\"Authentication required\"}"
        );
    })
    .accessDeniedHandler((request, response, exception) -> {
        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.getWriter().write(
            "{\"code\":\"FORBIDDEN\",\"message\":\"Insufficient access permissions\"}"
        );
    })
);
~~~

This is a short example illustrating the two handling points; in a real application, use ObjectMapper to serialize an error DTO instead of concatenating JSON strings, and include headers required by the authentication mechanism.

OpenAPI should document 401 and 403 responses for protected operations, along with error schemas if the backend returns a body. Response metadata does not automatically configure AuthenticationEntryPoint or AccessDeniedHandler.

## 15. CSRF and CORS are not solved by OpenAPI security

These two mechanisms are often confused with authentication:

- **CSRF** protects applications against forged requests sent automatically with a user's cookies/session.
- **CORS** is a browser policy controlling whether JavaScript from another origin can access responses.

Declaring a bearer scheme or API key in OpenAPI does not configure CSRF or CORS.

If an API uses bearer tokens in the Authorization header and does not rely on automatic authentication cookies, teams can choose a stateless model and configure CSRF accordingly. If using session cookies, keep the CSRF token mechanism properly configured.

If Swagger UI and the API live on two different origins, CORS must permit the required origins, methods, and headers, such as Authorization and Content-Type. CORS does not block curl or Postman and does not replace authorization.

## 16. Checking OpenAPI JSON after declaring security

After starting the application, download the document:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Inspect security schemes:

~~~bash
jq '.components.securitySchemes' openapi.json
~~~

Inspect global security requirements:

~~~bash
jq '.security' openapi.json
~~~

Inspect an operation's security:

~~~bash
jq '.paths["/api/me"].get.security' openapi.json
~~~

Inspect a public endpoint's security:

~~~bash
jq '.paths["/api/catalog"].get.security' openapi.json
~~~

Cross-check:

- Do schemes have the right type, scheme, in, name, and required URLs?
- Do names in security requirements match component keys?
- Which operations inherit root security?
- Do public operations genuinely remove security requirements?
- Do OAuth2 scopes match the scopes checked by the backend?
- Are 401/403 responses documented appropriately?

A structurally valid document can still misdescribe security policy. Compare it against SecurityFilterChain and method security.

## 17. Testing the backend with real requests

Do not check Swagger UI alone. Call endpoints directly with different credential states.

Example:

~~~bash
# Without token
curl -i http://localhost:8080/api/orders

# With invalid token
curl -i http://localhost:8080/api/orders \
  -H "Authorization: Bearer invalid-token"

# With valid token
curl -i http://localhost:8080/api/orders \
  -H "Authorization: Bearer <access-token>"
~~~

Results depend on configuration:

- No token: usually 401 if endpoint requires authentication.
- Token with wrong signature, expired, or invalid issuer: usually 401.
- Valid token lacking scope: usually 403.
- Valid token with sufficient permissions: request is processed according to business logic.

Do not place real tokens in source code, logs, or committed examples. Use environment variables or a secret manager when testing.

## 18. Writing tests for authentication and authorization

You can use MockMvc to check the status of protected endpoints. For a JWT resource server, Spring Security Test provides the jwt() request post-processor to create a mock Authentication in tests.

~~~java
@WebMvcTest(OrderController.class)
@Import(ApiSecurityConfiguration.class)
class OrderSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsAnonymousRequest() throws Exception {
        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void rejectsTokenWithoutRequiredScope() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_profile.read")
                )))
            .andExpect(status().isForbidden());
    }

    @Test
    void allowsTokenWithRequiredScope() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read")
                )))
            .andExpect(status().isOk());
    }
}
~~~

Tests require the spring-security-test dependency, imports of static helpers, and appropriate mock service configuration. jwt() simulates an already-created Authentication; it does not verify real JWT signatures, issuers, or signing keys. To test the decoder and token validation, write separate integration tests with a decoder/test issuer or suitable identity provider environment.

You should have both OpenAPI tests to verify schemes and requirements, and runtime tests to verify the filter chain actually rejects invalid requests.

## 19. Common errors

| Symptom | Cause to check |
|---|---|
| Swagger UI has an Authorize button yet endpoints still accept tokenless requests | Only OpenAPI scheme was declared; SecurityFilterChain was not configured |
| Backend requires a token yet Swagger UI does not send Authorization | Operation lacks security requirement or scheme name does not match |
| @SecurityScheme exists yet operations do not show a lock | Scheme was defined without attaching @SecurityRequirement or root security |
| Valid token still receives 401 | Issuer, signature, expiration, audience, or decoder misconfigured |
| Valid token receives 403 | Missing scope/authority or authorization rule mismatch |
| API key appears in Swagger UI yet is not validated | No filter/provider implemented to verify API keys |
| Public endpoint still requires token in documentation | Operation inherits root security without overriding via security: [] |
| Protected endpoint is documented as public | Security requirement missing or misdeclared |
| Swagger UI cannot load OpenAPI JSON | Docs path blocked by SecurityFilterChain or proxy misconfigured |
| Try it out fails with CORS error | Required origin/header/method not allowed |
| Cookie requests rejected by CSRF | Missing CSRF token or CSRF config mismatches session model |

## 20. Workflow to synchronize OpenAPI and Spring Security

When adding or changing an authentication mechanism, follow this sequence:

1. Identify the credential type: bearer JWT, opaque token, API key, Basic, or OAuth2/OIDC.
2. Configure runtime via SecurityFilterChain, resource server, or appropriate authentication provider.
3. Set up authorization for paths, HTTP methods, scopes/roles, and service methods.
4. Register security schemes using @SecurityScheme or the OpenAPI model.
5. Attach security requirements at the root or operation level with the exact scope.
6. Document public endpoints and 401/403 responses accurately.
7. Decide access policies for Swagger UI and /v3/api-docs.
8. Inspect OpenAPI JSON and test runtime requests.
9. Write tests for anonymous, invalid credentials, insufficient permissions, and valid permissions.
10. Review CORS, CSRF, and deployment configuration.

If claims or scopes change at the identity provider, update authority mappings, authorization rules, and scope descriptions in OpenAPI together.

## 21. Checklist

- [ ] Distinguished OpenAPI security schemes from runtime SecurityFilterChain.
- [ ] @SecurityScheme declares the right type and scheme name.
- [ ] @SecurityRequirement references the exact component key.
- [ ] Root and operation-level security are applied properly.
- [ ] Public endpoints have appropriate security requirements.
- [ ] JWT resource server verifies issuer, signature, and expiration.
- [ ] Audience and custom claims are checked if required by the API.
- [ ] Authorization checks the right scopes/roles.
- [ ] API keys or Basic auth have real authentication providers/filters.
- [ ] 401 and 403 are handled properly.
- [ ] Swagger UI and OpenAPI JSON are protected per policy.
- [ ] CSRF/CORS fit the cookie or bearer token model.
- [ ] Tested requests with no token, invalid token, insufficient permissions, and sufficient permissions.
- [ ] Checked security requirements in /v3/api-docs.

## 22. References

- [springdoc-openapi – official documentation](https://springdoc.org/)
- [OpenAPI Specification – Security Scheme Object](https://spec.openapis.org/oas/latest.html#security-scheme-object)
- [OpenAPI Specification – Security Requirement Object](https://spec.openapis.org/oas/latest.html#security-requirement-object)
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)

@SecurityScheme and @SecurityRequirement help publish how clients authenticate according to OpenAPI. SecurityFilterChain, resource servers, authentication providers, and authorization rules are what actually protect real requests. Keep both layers synchronized, inspect /v3/api-docs, and test missing tokens, invalid tokens, insufficient permissions, and valid permissions before releasing the API.
